from __future__ import annotations

import asyncio
import hashlib
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from threading import Lock

import numpy as np
from numpy.typing import NDArray
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from markguardiola.api.services.availability import (
    ConfirmedTeamSheet,
    load_confirmed_lineups,
    load_unavailable_player_ids,
)
from markguardiola.core.config import get_settings
from markguardiola.db.models import Match, PlayerMatchPrediction, PredictionRun, Season
from markguardiola.domain.roles import FootballRole, football_role
from markguardiola.fantasy.rules import FantasyScorer, ScoringRules
from markguardiola.simulation import FixtureForecast, PlayerForecast
from markguardiola.simulation.cache import FixtureScenarioCache
from markguardiola.simulation.engine import SimulationInputError
from markguardiola.simulation.models import FixtureSimulationResult, PlayerSimulationSummary
from markguardiola.simulation.rare_events import RareEventPrior, load_rare_event_prior


class PredictionDataUnavailableError(ValueError):
    pass


_SIMULATION_LOCKS = tuple(Lock() for _ in range(64))


@dataclass(frozen=True, slots=True)
class ScoredFixturePlayer:
    samples: NDArray[np.float64]
    appearance_probability: float
    confidence: float
    available: bool
    appearance_samples: NDArray[np.bool_]
    base_rating_samples: NDArray[np.float64]
    football: PlayerSimulationSummary
    warnings: tuple[str, ...] = ()


async def load_fixture_scenarios(
    session: AsyncSession,
    *,
    run: PredictionRun,
    match_ids: set[uuid.UUID],
    rules: ScoringRules,
    count: int,
    seed: int,
    scoring_roles: dict[uuid.UUID, FootballRole] | None = None,
    decision_cutoff: datetime | None = None,
    requested_player_ids: set[uuid.UUID] | None = None,
) -> dict[tuple[uuid.UUID, uuid.UUID], ScoredFixturePlayer]:

    rows = (
        await session.execute(
            select(PlayerMatchPrediction, Match)
            .join(Match, Match.id == PlayerMatchPrediction.match_id)
            .where(
                PlayerMatchPrediction.prediction_run_id == run.id,
                Match.id.in_(match_ids),
            )
            .order_by(Match.id, PlayerMatchPrediction.player_id, PlayerMatchPrediction.target)
        )
    ).all()
    grouped: dict[uuid.UUID, dict[uuid.UUID, dict[str, PlayerMatchPrediction]]] = defaultdict(
        lambda: defaultdict(dict)
    )
    matches: dict[uuid.UUID, Match] = {}
    for prediction, match in rows:
        grouped[match.id][prediction.player_id][prediction.target] = prediction
        matches[match.id] = match
    scorer = FantasyScorer(rules)
    competition_by_season = dict(
        (
            await session.execute(
                select(Season.id, Season.competition_id).where(
                    Season.id.in_({match.season_id for match in matches.values()})
                )
            )
        )
        .tuples()
        .all()
    )
    priors: dict[tuple[uuid.UUID, datetime], RareEventPrior] = {}
    output: dict[tuple[uuid.UUID, uuid.UUID], ScoredFixturePlayer] = {}
    for match_id, values in grouped.items():
        match = matches[match_id]
        cutoff = min(decision_cutoff or run.prediction_cutoff, match.kickoff_at)
        lineups = await load_confirmed_lineups(session, match_id, cutoff)
        confirmed_at = {
            player_id: sheet.observed_at for sheet in lineups.values() for player_id in sheet.squad
        }
        unavailable = await load_unavailable_player_ids(
            session,
            list(values),
            cutoff,
            fixture_date=match.kickoff_at.date(),
            confirmed_at=confirmed_at,
        )

        statistical_cutoff = min(run.data_cutoff, cutoff)
        prior_key = (competition_by_season[match.season_id], statistical_cutoff)
        if prior_key not in priors:
            frozen_prior = run.simulation_priors.get(str(prior_key[0]))
            if frozen_prior is not None and statistical_cutoff == run.data_cutoff:
                try:
                    priors[prior_key] = RareEventPrior.from_document(frozen_prior)
                except ValueError:
                    raise PredictionDataUnavailableError() from None
            else:
                priors[prior_key] = await load_rare_event_prior(
                    session, competition_id=prior_key[0], cutoff=statistical_cutoff
                )
        prior = priors[prior_key]
        forecast = _forecast(match, values, unavailable, lineups, prior)
        try:
            result = await asyncio.to_thread(
                _simulate_cached,
                forecast,
                count,
                seed,
                get_settings().artifact_root / "simulations" / "football",
            )
        except SimulationInputError:
            raise PredictionDataUnavailableError() from None
        for player in forecast.players:
            player_id = uuid.UUID(player.player_id)

            if requested_player_ids is not None and player_id not in requested_player_ids:
                continue
            sample = result.player_samples[player.player_id]
            events = {
                name: getattr(sample, name)
                for name in (
                    "minutes",
                    "goals",
                    "assists",
                    "clean_sheet",
                    "yellow_cards",
                    "red_cards",
                    "saves",
                    "goals_conceded",
                    "penalties_saved",
                    "penalties_missed",
                    "own_goals",
                )
            }
            rating = values[player_id].get("base_rating")
            if rating is not None:
                random = np.random.default_rng(_seed(seed, f"{match_id}:{player_id}:rating"))
                sigma = max(0.0, (rating.p90 - rating.p10) / 2.5631)
                events["base_rating"] = np.clip(
                    random.normal(rating.expected_value, sigma, count), 0, 10
                )
            output[(match_id, player_id)] = ScoredFixturePlayer(
                samples=scorer.score(
                    events, role=(scoring_roles or {}).get(player_id, player.position)
                ),
                appearance_probability=result.summaries[player.player_id].appearance_probability,
                confidence=player.reliability,
                available=player.availability_probability > 0,
                appearance_samples=(sample.minutes > 0)
                & (sample.minutes >= rules.appearance_minimum_minutes),
                base_rating_samples=np.asarray(
                    events.get("base_rating", np.full(count, rules.base_rating_fallback)),
                    dtype=float,
                ),
                football=result.summaries[player.player_id],
                warnings=(
                    ("Rigori e autogol non sono inclusi perché manca uno storico affidabile.",)
                    if prior.rates is None
                    else (
                        "Rigori e autogol sono stimati da "
                        f"{prior.rates.observed_matches} partite storiche.",
                    )
                ),
            )
    return output


def _forecast(
    match: Match,
    values: dict[uuid.UUID, dict[str, PlayerMatchPrediction]],
    unavailable: set[uuid.UUID],
    lineups: dict[uuid.UUID, ConfirmedTeamSheet] | None = None,
    prior: RareEventPrior | None = None,
) -> FixtureForecast:
    lineups = lineups or {}
    prior = prior or RareEventPrior(None, {}, {})
    for confirmed_sheet in lineups.values():
        if not confirmed_sheet.starters.issubset(values):
            raise PredictionDataUnavailableError()
    players: list[PlayerForecast] = []
    team_goals: dict[str, list[float]] = defaultdict(list)
    for player_id, targets in values.items():
        first = next(iter(targets.values()))
        team_id = first.distribution.get("team_id")
        if team_id not in {str(match.home_team_id), str(match.away_team_id)}:
            raise PredictionDataUnavailableError()
        role = football_role(str(first.distribution.get("football_role", "")))
        if role is None:
            continue
        required = {
            "start_probability",
            "appearance_probability",
            "expected_minutes",
            "expected_goals",
            "expected_assists",
            "team_goals",
            "yellow_card_probability",
        }
        missing = required.difference(targets)
        if missing:
            raise PredictionDataUnavailableError()
        appearance = _probability(targets["appearance_probability"])
        start = min(_probability(targets["start_probability"]), appearance)
        sheet = lineups.get(uuid.UUID(team_id))
        confirmed_start = player_id in sheet.starters if sheet else None
        available = player_id not in unavailable and appearance > 0
        if sheet is not None:
            available = player_id in sheet.squad and player_id not in unavailable
            if confirmed_start:
                start = appearance = 1.0
            else:
                appearance = min(1.0, max(0.0, (appearance - start) / max(1 - start, 1e-8)))
                start = 0.0
        minutes = targets["expected_minutes"]
        expected_minutes = max(0.0, minutes.expected_value)
        team_goals[team_id].append(targets["team_goals"].expected_value)
        players.append(
            PlayerForecast(
                player_id=str(player_id),
                team_id=team_id,
                position=role,
                availability_probability=float(available),
                start_probability=start,
                appearance_probability=appearance,
                expected_minutes=min(90.0, expected_minutes / max(appearance, 1e-8)),
                minutes_stddev=max(0.0, (minutes.p90 - minutes.p10) / 2.5631),
                goal_weight=max(0.0, targets["expected_goals"].expected_value)
                / max(expected_minutes, 1.0),
                assist_weight=max(0.0, targets["expected_assists"].expected_value)
                / max(expected_minutes, 1.0),
                yellow_card_probability=_per90_probability(
                    targets.get("yellow_card_probability"), expected_minutes
                ),
                red_card_probability=_per90_probability(
                    targets.get("red_card_probability"), expected_minutes
                ),
                saves_per90=(
                    max(0.0, targets["goalkeeper_saves"].expected_value)
                    * 90
                    / max(expected_minutes, 1.0)
                    if role == "GK" and "goalkeeper_saves" in targets
                    else 0.0
                ),
                reliability=float(np.mean([value.reliability for value in targets.values()])),
                confirmed_start=confirmed_start,
                penalty_weight=prior.player(str(player_id), role).penalty_weight,
                own_goal_weight=prior.player(str(player_id), role).own_goal_weight,
            )
        )
    if set(team_goals) != {str(match.home_team_id), str(match.away_team_id)}:
        raise PredictionDataUnavailableError()
    return FixtureForecast(
        match_id=str(match.id),
        home_team_id=str(match.home_team_id),
        away_team_id=str(match.away_team_id),
        home_goals_mean=max(0.0, float(np.mean(team_goals[str(match.home_team_id)]))),
        away_goals_mean=max(0.0, float(np.mean(team_goals[str(match.away_team_id)]))),
        players=tuple(players),
        rare_event_rates=prior.rates,
    )


@lru_cache(maxsize=16)
def _simulate_cached(
    forecast: FixtureForecast, count: int, seed: int, cache_root: Path
) -> FixtureSimulationResult:

    lock = _SIMULATION_LOCKS[hash((forecast, count, seed, cache_root)) % len(_SIMULATION_LOCKS)]
    with lock:
        return FixtureScenarioCache(cache_root).get_or_simulate(
            forecast, count=count, seed=_seed(seed, forecast.match_id)
        )


def _seed(seed: int, identity: str) -> int:
    return int.from_bytes(hashlib.sha256(f"{seed}:{identity}".encode()).digest()[:8], "big")


def _probability(value: PlayerMatchPrediction) -> float:
    return max(
        0.0, min(value.probability if value.probability is not None else value.expected_value, 1.0)
    )


def _per90_probability(value: PlayerMatchPrediction | None, minutes: float) -> float:
    if value is None:
        return 0.0
    return float(1 - (1 - _probability(value)) ** (90 / max(minutes, 1.0)))
