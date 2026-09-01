from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict
from dataclasses import asdict
from datetime import UTC, date, datetime, time, timedelta

import numpy as np
import polars as pl
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from markguardiola.api.services.fixture_simulations import _forecast
from markguardiola.backtesting.decisions import draft_benchmark_rosters, evaluate_decision_case
from markguardiola.backtesting.models import ReplayModel
from markguardiola.backtesting.training import prepare_replay_training
from markguardiola.core.config import Settings, get_settings
from markguardiola.db.models import DataSource, Match, PlayerMatchPrediction, PlayerMatchStat
from markguardiola.db.session import get_session_factory
from markguardiola.decision.models import PlayerDecisionInput
from markguardiola.domain.roles import football_role
from markguardiola.fantasy.rules import FantasyScorer, ScoringRules
from markguardiola.fantasy.rules.models import SubstitutionRules
from markguardiola.features.builders import PointInTimeSnapshotBuilder
from markguardiola.features.materialize import materialize_snapshot
from markguardiola.features.membership import resolve_upcoming_memberships
from markguardiola.features.pipeline import (
    FEATURE_SCHEMA_VERSION,
    _known_referee,
    load_canonical_history,
)
from markguardiola.ml.arena.probability import ProbabilityChampion
from markguardiola.ml.registry.artifacts import archive_source_code, write_evaluation
from markguardiola.simulation.cache import FixtureScenarioCache
from markguardiola.simulation.rare_events import RareEventPrior, load_rare_event_prior

logger = structlog.get_logger(__name__)


async def run_decision_backtest(
    season_label: str,
    *,
    maximum_weeks: int = 8,
    drafts_per_week: int = 2,
    simulations: int = 1000,
    seed: int = 2026,
    include_external: bool = True,
    training_snapshot_hash: str | None = None,
) -> dict[str, object]:
    if min(maximum_weeks, drafts_per_week, simulations) < 1:
        raise ValueError()
    settings = get_settings()
    replay_source_revision = archive_source_code(settings.artifact_root)
    scoring, substitutions = ScoringRules(), SubstitutionRules()
    report_id = uuid.uuid4().hex
    output = settings.artifact_root / "backtests" / "decisions" / report_id
    cases: list[dict[str, object]] = []
    exclusions: list[dict[str, str]] = []
    async with get_session_factory()() as session:
        training = await prepare_replay_training(
            session,
            settings,
            season_label=season_label,
            include_external=include_external,
            training_snapshot_hash=training_snapshot_hash,
        )
        matches = list(
            (
                await session.scalars(
                    select(Match)
                    .where(Match.season_id == training.season.id)
                    .order_by(Match.kickoff_at, Match.id)
                )
            ).all()
        )
        grouped: dict[date, list[Match]] = defaultdict(list)
        for match in matches:
            start = calendar_period_start(match.kickoff_at.date())
            grouped[start].append(match)
        eligible: list[tuple[date, list[Match]]] = []
        for monday, week_matches in sorted(grouped.items()):
            clubs = [
                club for match in week_matches for club in (match.home_team_id, match.away_team_id)
            ]
            if (
                len(week_matches) != 10
                or len(set(clubs)) != 20
                or any(match.status != "finished" for match in week_matches)
            ):
                exclusions.append(
                    {"week": str(monday), "reason": "not a complete single-fixture-per-club week"}
                )
                continue
            eligible.append((monday, week_matches))
        indices = np.linspace(0, len(eligible) - 1, min(maximum_weeks, len(eligible)), dtype=int)
        for index in indices:
            monday, week_matches = eligible[int(index)]
            cutoff = datetime.combine(monday, time.min, tzinfo=UTC)
            if cutoff < training.cutoff:
                exclusions.append(
                    {"week": str(monday), "reason": "before historical training cutoff"}
                )
                continue
            logger.info("decision_replay_week", week=str(monday), fixtures=len(week_matches))
            try:
                week_cases = []
                frame, source_manifest = await _candidate_frame(session, week_matches, cutoff)
                roles = dict(frame.select("player_id", "football_role").iter_rows())
                observed = await _observed_outcomes(session, week_matches, scoring, roles=roles)
                snapshot = materialize_snapshot(
                    frame,
                    output_root=output / "inputs",
                    feature_schema_version=FEATURE_SCHEMA_VERSION,
                    source_manifest=source_manifest,
                )
                prior = await load_rare_event_prior(
                    session, competition_id=training.season.competition_id, cutoff=cutoff
                )
                predictions = _infer(frame, training.models)
                players = await asyncio.to_thread(
                    _simulate_players,
                    week_matches,
                    predictions,
                    prior,
                    scoring,
                    simulations,
                    seed,
                    settings,
                )

                unlisted = [
                    player.player_id for player in players if player.player_id not in observed
                ]
                observed = {
                    player.player_id: observed.get(player.player_id, (0.0, False))
                    for player in players
                }
                write_evaluation(
                    output / f"outcomes-{monday}.json",
                    {
                        "week": str(monday),
                        "fixture_ids": [str(match.id) for match in week_matches],
                        "outcomes": observed,
                        "inferred_nonappearance_player_ids": unlisted,
                    },
                )
                minutes = {
                    str(row["player_id"]): float(row["minutes_last_3"] or 0)
                    for row in frame.iter_rows(named=True)
                }
                for draft in range(drafts_per_week):
                    roster, opponent, market = draft_benchmark_rosters(
                        players, minutes, seed=seed + draft
                    )
                    case = await asyncio.to_thread(
                        evaluate_decision_case,
                        roster,
                        opponent,
                        market,
                        past_minutes=minutes,
                        observed=observed,
                        scoring=scoring,
                        substitutions=substitutions,
                    )
                    case.update(
                        {
                            "week": str(monday),
                            "draft_seed": seed + draft,
                            "input_snapshot_sha256": snapshot.content_sha256,
                            "rare_event_prior": asdict(prior.rates) if prior.rates else None,
                        }
                    )
                    week_cases.append(case)
                    write_evaluation(output / f"case-{monday}-{draft}.json", case)
                cases.extend(week_cases)
            except ValueError:
                exclusions.append({"week": str(monday), "reason": "insufficient_data"})
                logger.warning("decision_replay_week_excluded", week=str(monday))
        report: dict[str, object] = {
            "status": "completed" if cases else "insufficient_coverage",
            "report_id": report_id,
            "season": season_label,
            "training_cutoff": training.cutoff.isoformat(),
            "training_snapshot_sha256": training.snapshot_hash,
            "preparation_source_revision": training.source_revision,
            "replay_source_revision": replay_source_revision,
            "models": {
                target: {
                    "recipe_id": model.recipe_id,
                    "source_revision": model.manifest["source_revision"],
                }
                for target, model in training.models.items()
            },
            "simulation_count": simulations,
            "seed": seed,
            "scoring": scoring.model_dump(mode="json"),
            "substitutions": substitutions.model_dump(mode="json"),
            "eligible_calendar_weeks": len(eligible),
            "requested_weeks": maximum_weeks,
            "drafts_per_week": drafts_per_week,
            "selection_method": "evenly_spaced_complete_tuesday_to_monday_periods",
            "evaluated_cases": len(cases),
            "metrics": summarize_cases(cases, seed=seed),
            "cases": cases,
            "exclusions": exclusions,
            "limitations": [
                "Constructed pre-cutoff rosters, not observed user-league rosters.",
                "Fixture calendar and publication times are reconstructed, "
                "not original pre-match snapshots.",
                "Scores use constant appearance credit 6 plus events, not published fantasy votes.",
                "Unlisted players count as absent only after 11-starter sheets "
                "and goal totals are checked.",
                "Hindsight comparator is best legal candidate found, not a proven global optimum.",
                "No historical prices: acquisition lift is unpriced; affordability is unknown.",
                "Shared match outcomes correlate drafts within a week; intervals resample weeks.",
            ],
            "production_registry_modified": False,
        }
        write_evaluation(output / "report.json", report)
    return {
        "report_path": str((output / "report.json").resolve()),
        "status": report["status"],
        "evaluated_cases": len(cases),
        "metrics": report["metrics"],
    }


async def _candidate_frame(
    session: AsyncSession, matches: list[Match], cutoff: datetime
) -> tuple[pl.DataFrame, dict[str, object]]:
    history = await load_canonical_history(session, cutoff=cutoff)
    membership = await resolve_upcoming_memberships(
        session, matches, cutoff, history.latest_membership, history.membership_available_at
    )
    rows = []
    unknown_roles = 0
    for match in matches:
        for club, opponent, home in (
            (match.home_team_id, match.away_team_id, 1),
            (match.away_team_id, match.home_team_id, 0),
        ):
            for player, role in membership.by_fixture_team.get((match.id, club), []):
                if football_role(role) is None:
                    unknown_roles += 1
                    continue
                rows.append(
                    {
                        "snapshot_row_id": f"{match.id}:{player}",
                        "player_id": str(player),
                        "team_id": str(club),
                        "opponent_team_id": str(opponent),
                        "match_id": str(match.id),
                        "prediction_cutoff": cutoff,
                        "kickoff_at": match.kickoff_at,
                        "home_flag": home,
                        "referee_id": _known_referee(match, cutoff),
                        "football_role": role,
                        "membership_max_available_at": membership.available_at[(match.id, player)],
                    }
                )
    if not rows:
        raise ValueError()
    frame = PointInTimeSnapshotBuilder().build(
        candidates=pl.DataFrame(rows),
        player_history=history.player_history,
        team_history=history.team_history,
    )
    return frame, {
        "cutoff": cutoff.isoformat(),
        "fixture_context_reconstructed": True,
        "excluded_unknown_role_memberships": unknown_roles,
        "ingestion_run_ids": sorted(
            set(history.ingestion_run_ids) | set(membership.ingestion_run_ids)
        ),
    }


def _infer(
    frame: pl.DataFrame, models: dict[str, ReplayModel]
) -> dict[uuid.UUID, dict[uuid.UUID, dict[str, PlayerMatchPrediction]]]:
    output: dict[uuid.UUID, dict[uuid.UUID, dict[str, PlayerMatchPrediction]]] = defaultdict(
        lambda: defaultdict(dict)
    )
    rows = frame.select("match_id", "player_id", "team_id", "football_role").to_dicts()
    for target, replay in models.items():
        model = replay.champion
        features = np.asarray(
            frame.select(model.feature_names).cast(pl.Float64).to_numpy(), dtype=float
        )
        if isinstance(model, ProbabilityChampion):
            expected = model.predict_proba(features)
            lower, upper = (expected >= 0.9).astype(float), (expected > 0.1).astype(float)
            probability = True
            reliability = max(0.0, min(1.0, 1 - model.metrics.get("calibration_error", 0.2)))
        else:
            expected = model.predict(features)
            interval = model.interval.predict(expected)
            lower, upper = interval.lower, interval.upper
            probability = False
            reliability = 1 / (1 + max(0.0, model.metrics.get("mae", 1.0)))
        for index, row in enumerate(rows):
            match_id, player_id = uuid.UUID(row["match_id"]), uuid.UUID(row["player_id"])
            output[match_id][player_id][target] = PlayerMatchPrediction(
                match_id=match_id,
                player_id=player_id,
                target=target,
                expected_value=float(expected[index]),
                p10=float(lower[index]),
                p90=float(upper[index]),
                median=float(expected[index]),
                probability=float(expected[index]) if probability else None,
                reliability=reliability,
                distribution={"team_id": row["team_id"], "football_role": row["football_role"]},
            )
    return dict(output)


def _simulate_players(
    matches: list[Match],
    predictions: dict[uuid.UUID, dict[uuid.UUID, dict[str, PlayerMatchPrediction]]],
    prior: RareEventPrior,
    scoring: ScoringRules,
    count: int,
    seed: int,
    settings: Settings,
) -> list[PlayerDecisionInput]:
    scorer = FantasyScorer(scoring)
    output = []
    cache = FixtureScenarioCache(settings.artifact_root / "backtests" / "football")
    for match in matches:
        forecast = _forecast(match, predictions.get(match.id, {}), set(), prior=prior)
        result = cache.get_or_simulate(forecast, count=count, seed=seed + match.id.int % 2**32)
        for player in forecast.players:
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
            scores = scorer.score(events, role=player.position)
            output.append(
                PlayerDecisionInput(
                    player_id=player.player_id,
                    display_name=player.player_id,
                    roles=(player.position,),
                    expected_points=float(scores.mean()),
                    median_points=float(np.median(scores)),
                    p10_points=float(np.quantile(scores, 0.1)),
                    p90_points=float(np.quantile(scores, 0.9)),
                    appearance_probability=float(np.mean(sample.minutes > 0)),
                    available=player.availability_probability > 0,
                    samples=scores,
                    appearance_samples=sample.minutes > 0,
                    base_rating_samples=np.full(count, scoring.base_rating_fallback),
                    scoring_role=player.position,
                )
            )
    return output


async def _observed_outcomes(
    session: AsyncSession, matches: list[Match], scoring: ScoringRules, *, roles: dict[str, str]
) -> dict[str, tuple[float, bool]]:
    rows = (
        await session.scalars(
            select(PlayerMatchStat)
            .join(DataSource, DataSource.id == PlayerMatchStat.source_id)
            .where(
                PlayerMatchStat.match_id.in_([match.id for match in matches]),
                DataSource.key == "pannadata",
            )
            .order_by(PlayerMatchStat.available_at, PlayerMatchStat.ingested_at, PlayerMatchStat.id)
        )
    ).all()
    unique = {(row.match_id, row.player_id): row for row in rows}
    grouped: dict[uuid.UUID, list[PlayerMatchStat]] = defaultdict(list)
    for row in unique.values():
        grouped[row.match_id].append(row)
    output = {}
    scorer = FantasyScorer(scoring)
    for match in matches:
        stats = grouped.get(match.id, [])
        for team in (match.home_team_id, match.away_team_id):
            same = [stat for stat in stats if stat.team_id == team]
            opposing = [stat for stat in stats if stat.team_id != team]
            score = match.home_score if team == match.home_team_id else match.away_score
            if (
                sum(stat.started for stat in same) != 11
                or any(stat.stats.get("event_statistics_available") != 1 for stat in same)
                or sum(_number(stat.stats.get("goals", 0)) for stat in same)
                + sum(_number(stat.stats.get("own_goals", 0)) for stat in opposing)
                != score
            ):
                raise ValueError()
        for stat in stats:
            if stat.minutes == 0:
                output[str(stat.player_id)] = (0.0, False)
                continue

            if str(stat.player_id) not in roles:
                continue
            role = football_role(roles[str(stat.player_id)])
            if role is None:
                raise ValueError()
            values = stat.stats
            conceded = match.away_score if stat.team_id == match.home_team_id else match.home_score
            events = {
                "minutes": stat.minutes,
                "goals": values.get("goals", 0),
                "assists": values.get("assists", 0),
                "yellow_cards": values.get("yellow_cards", 0),
                "red_cards": values.get("red_cards", 0),
                "own_goals": values.get("own_goals", 0),
                "penalties_saved": values.get("penalties_saved", values.get("penalty_save", 0)),
                "penalties_missed": values.get(
                    "penalties_missed",
                    sum(
                        _number(values.get(key, 0))
                        for key in ("att_pen_miss", "att_pen_post", "att_pen_target")
                    ),
                ),
                "clean_sheet": conceded == 0 and stat.minutes >= 60,
                "goals_conceded": conceded if role == "GK" else 0,
                "saves": values.get("saves", 0),
            }
            if any(value is None for value in events.values()):
                raise ValueError()
            output[str(stat.player_id)] = (
                float(
                    scorer.score({key: _number(value) for key, value in events.items()}, role=role)[
                        0
                    ]
                ),
                stat.minutes > 0,
            )
    return output


def summarize_cases(cases: list[dict[str, object]], *, seed: int) -> dict[str, object]:
    if not cases:
        return {}
    fields = (
        "observed_balanced_score",
        "observed_naive_score",
        "observed_lineup_lift",
        "regret_to_best_known",
        "observed_balanced_win",
        "observed_naive_win",
        "observed_matchup_win",
        "predicted_balanced_win_probability",
        "predicted_matchup_win_probability",
    )
    means = {field: float(np.mean([_number(case[field]) for case in cases])) for field in fields}
    weeks: dict[str, list[float]] = defaultdict(list)
    for case in cases:
        weeks[str(case["week"])].append(_number(case["observed_lineup_lift"]))
    by_week = np.array([np.mean(values) for values in weeks.values()])
    random = np.random.default_rng(seed)
    bootstrap = random.choice(by_week, size=(2000, len(by_week)), replace=True).mean(axis=1)
    market = [item for case in cases if isinstance(item := case.get("market"), dict)]
    return {
        **means,
        "independent_week_clusters": len(weeks),
        "lineup_lift_week_bootstrap_95pct": np.quantile(bootstrap, [0.025, 0.975]).tolist()
        if len(weeks) >= 2
        else None,
        "market_cases": len(market),
        "mean_observed_market_lift": float(
            np.mean([_number(item["observed_lift"]) for item in market])
        )
        if market
        else None,
    }


def _number(value: object) -> float:
    if not isinstance(value, (int, float)) or not np.isfinite(value):
        raise ValueError()
    return float(value)


def calendar_period_start(value: date) -> date:
    return value - timedelta(days=(value.weekday() - 1) % 7)
