from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from markguardiola.api.services.availability import (
    load_unavailable_player_ids as load_unavailable_player_ids,
)
from markguardiola.api.services.fixture_simulations import (
    PredictionDataUnavailableError as PredictionDataUnavailableError,
)
from markguardiola.api.services.fixture_simulations import (
    ScoredFixturePlayer,
    load_fixture_scenarios,
)
from markguardiola.api.services.freshness import source_statuses
from markguardiola.api.services.prediction_runs import latest_compatible_prediction_run
from markguardiola.core.config import get_settings
from markguardiola.db.models import (
    Match,
    Player,
    PlayerFantasyRole,
    PlayerMatchPrediction,
    RosterEntry,
)
from markguardiola.decision import PlayerDecisionInput
from markguardiola.decision.models import FixtureDecisionProjection
from markguardiola.domain.roles import FootballRole, football_role
from markguardiola.fantasy.rules import ScoringRules


@dataclass(frozen=True, slots=True)
class ProjectionBundle:
    inputs: list[PlayerDecisionInput]
    prediction_run_id: uuid.UUID
    prediction_cutoff: datetime
    data_cutoff: datetime
    confidence: float
    simulation_count: int
    seed: int
    decision_cutoff: datetime
    fixture_scenarios: dict[tuple[uuid.UUID, uuid.UUID], ScoredFixturePlayer] = field(
        compare=False, repr=False
    )
    warnings: tuple[str, ...] = ()


async def load_roster_projection_bundle(
    session: AsyncSession,
    *,
    league_id: uuid.UUID,
    fantasy_team_id: uuid.UUID,
    rules: ScoringRules,
    simulation_count: int | None = None,
    seed: int = 2026,
    horizon: int = 1,
    decision_cutoff: datetime | None = None,
    prediction_run_id: uuid.UUID | None = None,
) -> ProjectionBundle:
    rows = (
        await session.execute(
            select(RosterEntry, Player)
            .join(Player, Player.id == RosterEntry.player_id)
            .where(RosterEntry.fantasy_team_id == fantasy_team_id, RosterEntry.active.is_(True))
        )
    ).all()
    if not rows:
        raise PredictionDataUnavailableError()
    return await _load_player_projection_bundle(
        session,
        league_id=league_id,
        players=[player for _, player in rows],
        purchase_prices={
            player.id: float(entry.purchase_price) if entry.purchase_price is not None else None
            for entry, player in rows
        },
        rules=rules,
        simulation_count=simulation_count,
        seed=seed,
        horizon=horizon,
        decision_cutoff=decision_cutoff,
        prediction_run_id=prediction_run_id,
    )


async def load_player_projection_bundle(
    session: AsyncSession,
    *,
    league_id: uuid.UUID,
    player_ids: list[uuid.UUID],
    rules: ScoringRules,
    decision_cutoff: datetime | None = None,
    prediction_run_id: uuid.UUID | None = None,
    horizon: int = 10,
) -> ProjectionBundle:
    players = list(
        (
            await session.scalars(
                select(Player).where(Player.id.in_(player_ids), Player.active.is_(True))
            )
        ).all()
    )
    return await _load_player_projection_bundle(
        session,
        league_id=league_id,
        players=players,
        purchase_prices={},
        rules=rules,
        simulation_count=None,
        seed=2026,
        horizon=horizon,
        decision_cutoff=decision_cutoff,
        prediction_run_id=prediction_run_id,
    )


async def _load_player_projection_bundle(
    session: AsyncSession,
    *,
    league_id: uuid.UUID,
    players: list[Player],
    purchase_prices: dict[uuid.UUID, float | None],
    rules: ScoringRules,
    simulation_count: int | None,
    seed: int,
    horizon: int,
    decision_cutoff: datetime | None,
    prediction_run_id: uuid.UUID | None,
) -> ProjectionBundle:
    decision_cutoff = decision_cutoff or datetime.now(UTC)
    run = await latest_compatible_prediction_run(session, run_id=prediction_run_id)
    player_ids = [player.id for player in players]
    rows = (
        await session.execute(
            select(PlayerMatchPrediction.player_id, Match.id, Match.kickoff_at)
            .join(Match, Match.id == PlayerMatchPrediction.match_id)
            .where(
                PlayerMatchPrediction.prediction_run_id == run.id,
                PlayerMatchPrediction.player_id.in_(player_ids),
                Match.kickoff_at >= max(run.prediction_cutoff, decision_cutoff),
                Match.status.not_in(["finished", "cancelled", "abandoned", "awarded"]),
            )
            .distinct()
            .order_by(Match.kickoff_at, Match.id)
        )
    ).all()
    by_player: dict[uuid.UUID, list[tuple[uuid.UUID, date]]] = defaultdict(list)
    for player_id, match_id, kickoff in rows:
        if len(by_player[player_id]) < horizon:
            by_player[player_id].append((match_id, kickoff.date()))
    match_ids = {match_id for fixtures in by_player.values() for match_id, _ in fixtures}
    if not match_ids:
        raise PredictionDataUnavailableError()
    count = simulation_count or get_settings().default_simulations
    roles = await _load_roles(session, league_id, players)
    scoring_roles = {
        player_id: canonical
        for player_id, player_roles in roles.items()
        if player_roles and (canonical := _scoring_role(player_roles[0])) is not None
    }
    scenarios = await load_fixture_scenarios(
        session,
        run=run,
        match_ids=match_ids,
        rules=rules,
        count=count,
        seed=seed,
        scoring_roles=scoring_roles,
        decision_cutoff=decision_cutoff,
        requested_player_ids=set(player_ids),
    )
    inputs: list[PlayerDecisionInput] = []
    confidences: list[float] = []
    for player in players:
        fixtures = by_player.get(player.id, [])
        projected = [
            scenarios[(match_id, player.id)]
            for match_id, _ in fixtures
            if (match_id, player.id) in scenarios
        ]
        player_roles = roles.get(player.id, ())
        if not projected or not player_roles:
            continue
        first = projected[0]
        inputs.append(
            PlayerDecisionInput(
                player_id=str(player.id),
                display_name=player.display_name,
                roles=player_roles,
                expected_points=float(np.mean(first.samples)),
                median_points=float(np.median(first.samples)),
                p10_points=float(np.quantile(first.samples, 0.1)),
                p90_points=float(np.quantile(first.samples, 0.9)),
                appearance_probability=first.appearance_probability,
                available=first.available,
                purchase_price=purchase_prices.get(player.id),
                horizon_points={
                    length: sum(float(np.mean(item.samples)) for item in projected[:length])
                    for length in (1, 3, 5, 10)
                    if len(projected) >= length
                },
                samples=first.samples,
                appearance_samples=first.appearance_samples,
                base_rating_samples=first.base_rating_samples,
                scoring_role=scoring_roles.get(player.id),
                photo_url=player.photo_url,
                fixture_projections=tuple(
                    FixtureDecisionProjection(
                        fixture_id=str(match_id),
                        samples=scenarios[(match_id, player.id)].samples,
                        appearance_samples=scenarios[(match_id, player.id)].appearance_samples,
                        base_rating_samples=scenarios[(match_id, player.id)].base_rating_samples,
                        available=scenarios[(match_id, player.id)].available,
                    )
                    for match_id, _ in fixtures
                    if (match_id, player.id) in scenarios
                ),
            )
        )
        confidences.append(first.confidence)
    if not inputs:
        raise PredictionDataUnavailableError()
    warnings = sorted({warning for player in scenarios.values() for warning in player.warnings})
    operational = next(
        item
        for item in await source_statuses(session, get_settings())
        if item.key == "api_football"
    )
    if operational.status != "available":
        warnings.append("Infortuni e formazioni ufficiali non sono verificati.")
    if rules.base_rating_enabled and "base_rating" not in run.model_versions:
        warnings.append(
            f"Il voto base usa il valore {rules.base_rating_fallback:g} previsto dalle regole."
        )
    return ProjectionBundle(
        inputs=inputs,
        prediction_run_id=run.id,
        prediction_cutoff=run.prediction_cutoff,
        data_cutoff=run.data_cutoff,
        confidence=float(np.mean(confidences)),
        simulation_count=count,
        seed=seed,
        decision_cutoff=decision_cutoff,
        fixture_scenarios=scenarios,
        warnings=tuple(warnings),
    )


async def _load_roles(
    session: AsyncSession,
    league_id: uuid.UUID,
    players: list[Player],
) -> dict[uuid.UUID, tuple[str, ...]]:
    rows = (
        await session.execute(
            select(PlayerFantasyRole.player_id, PlayerFantasyRole.role)
            .where(
                PlayerFantasyRole.league_id == league_id,
                PlayerFantasyRole.player_id.in_([player.id for player in players]),
            )
            .order_by(
                PlayerFantasyRole.player_id,
                PlayerFantasyRole.is_primary.desc(),
                PlayerFantasyRole.role,
            )
        )
    ).all()
    output: dict[uuid.UUID, list[str]] = defaultdict(list)
    for player_id, role in rows:
        if role not in output[player_id]:
            output[player_id].append(role)
    for player in players:
        if not output[player.id]:
            fallback = football_role(player.primary_position)
            if fallback is not None:
                output[player.id].append(fallback)
    return {player_id: tuple(values) for player_id, values in output.items()}


def _scoring_role(role: str) -> FootballRole | None:
    canonical = football_role(role)
    if canonical is not None:
        return canonical
    mantra: dict[str, FootballRole] = {
        "Dd": "DEF",
        "Ds": "DEF",
        "Dc": "DEF",
        "B": "DEF",
        "E": "MID",
        "M": "MID",
        "C": "MID",
        "T": "MID",
        "W": "MID",
        "A": "FWD",
        "Pc": "FWD",
    }
    return mantra.get(role)
