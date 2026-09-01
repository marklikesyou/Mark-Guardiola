from __future__ import annotations

import hashlib
import json
import uuid
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta

from pydantic import TypeAdapter
from sqlalchemy import Float, and_, case, cast, func, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from markguardiola.db.models import DataSource, Match, PlayerMatchStat, Season
from markguardiola.domain.roles import football_role
from markguardiola.simulation.models import RareEventRates


@dataclass(frozen=True, slots=True)
class PlayerEventPrior:
    penalty_weight: float
    own_goal_weight: float


@dataclass(frozen=True, slots=True)
class RareEventPrior:
    rates: RareEventRates | None
    players: dict[str, PlayerEventPrior]
    roles: dict[str, PlayerEventPrior]

    def player(self, player_id: str, role: str) -> PlayerEventPrior:
        return self.players.get(player_id, self.roles.get(role, PlayerEventPrior(0.0, 0.0)))

    def to_document(self) -> dict[str, object]:
        return {"version": 1, "prior": asdict(self)}

    @classmethod
    def from_document(cls, value: object) -> RareEventPrior:
        if not isinstance(value, dict) or value.get("version") != 1:
            raise ValueError()
        return TypeAdapter(cls).validate_python(value.get("prior"))


def _counter(name: str, *legacy: str) -> ColumnElement[float]:
    stats = PlayerMatchStat.stats
    return case(
        (stats.has_key(name), cast(stats[name].astext, Float)),
        (
            DataSource.key == "pannadata",
            sum((func.coalesce(cast(stats[key].astext, Float), 0.0) for key in legacy), 0.0),
        ),
        else_=None,
    )


async def load_rare_event_prior(
    session: AsyncSession,
    *,
    competition_id: uuid.UUID,
    cutoff: datetime,
    lookback_days: int = 1096,
) -> RareEventPrior:

    observations = (
        select(
            PlayerMatchStat.player_id,
            PlayerMatchStat.match_id,
            PlayerMatchStat.minutes,
            PlayerMatchStat.football_position,
            PlayerMatchStat.available_at,
            PlayerMatchStat.ingestion_run_id,
            PlayerMatchStat.stats["event_statistics_available"].as_integer().label("covered"),
            _counter("goals", "goals").label("goals"),
            _counter("penalties_scored", "att_pen_goal").label("penalties_scored"),
            _counter("penalties_missed", "att_pen_miss", "att_pen_post", "att_pen_target").label(
                "penalties_missed"
            ),
            _counter("penalties_saved", "penalty_save").label("penalties_saved"),
            _counter("own_goals", "own_goals").label("own_goals"),
            func.row_number()
            .over(
                partition_by=(PlayerMatchStat.player_id, PlayerMatchStat.match_id),
                order_by=(
                    PlayerMatchStat.available_at.desc(),
                    DataSource.priority.asc(),
                    PlayerMatchStat.ingested_at.desc(),
                    PlayerMatchStat.id.desc(),
                ),
            )
            .label("revision"),
        )
        .join(Match, Match.id == PlayerMatchStat.match_id)
        .join(Season, Season.id == Match.season_id)
        .join(DataSource, DataSource.id == PlayerMatchStat.source_id)
        .where(
            Season.competition_id == competition_id,
            Match.status == "finished",
            PlayerMatchStat.event_time < cutoff,
            PlayerMatchStat.event_time >= cutoff - timedelta(days=lookback_days),
            PlayerMatchStat.available_at <= cutoff,
        )
        .subquery()
    )
    counters = ("goals", "penalties_scored", "penalties_missed", "penalties_saved", "own_goals")

    covered = (
        select(observations)
        .where(
            observations.c.revision == 1,
            observations.c.covered == 1,
            observations.c.minutes > 0,
            and_(*(observations.c[name] >= 0 for name in counters)),
            observations.c.penalties_scored <= observations.c.goals,
        )
        .cte("rare_event_covered")
    )
    aggregate = (
        select(
            covered.c.player_id,
            covered.c.football_position,
            func.sum(covered.c.minutes).label("minutes"),
            *(func.sum(covered.c[name]).label(name) for name in counters),
            func.count().label("rows"),
            func.max(covered.c.available_at).label("latest_available_at"),
        )
        .group_by(covered.c.player_id, covered.c.football_position)
        .subquery()
    )
    summary = select(
        func.count(func.distinct(covered.c.match_id)).label("match_count"),
        func.array_agg(func.distinct(covered.c.ingestion_run_id)).label("ingestion_run_ids"),
    ).subquery()

    statement = select(aggregate, summary).select_from(aggregate.join(summary, true()))
    rows = (await session.execute(statement)).mappings().all()
    total_goals = sum(float(row["goals"] + row["own_goals"]) for row in rows)
    if total_goals <= 0:
        return RareEventPrior(None, {}, {})
    totals = {name: sum(float(row[name]) for row in rows) for name in counters}
    if totals["penalties_saved"] > totals["penalties_missed"]:
        return RareEventPrior(None, {}, {})
    match_count = rows[0]["match_count"]
    lineage = rows[0]["ingestion_run_ids"]
    evidence = {
        "lookback_days": lookback_days,
        "ingestion_runs": sorted(str(value) for value in lineage),
        "totals": totals,
        "minutes": sum(int(row["minutes"]) for row in rows),
    }
    rates = RareEventRates(
        penalty_goal_share=totals["penalties_scored"] / total_goals,
        own_goal_share=totals["own_goals"] / total_goals,
        missed_penalties_per_goal=totals["penalties_missed"] / total_goals,
        penalty_save_probability=(
            totals["penalties_saved"] / totals["penalties_missed"]
            if totals["penalties_missed"]
            else 0.0
        ),
        observed_matches=int(match_count or 0),
        observed_player_rows=sum(int(row["rows"]) for row in rows),
        latest_available_at=max(row["latest_available_at"] for row in rows).isoformat(),
        source_digest=hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest(),
    )
    role_totals: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
    player_totals: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
    player_roles: dict[str, str] = {}
    player_role_minutes: dict[str, float] = {}
    for row in rows:
        role = football_role(row["football_position"] or "")
        if role is None:
            continue
        player_id = str(row["player_id"])
        amounts = [
            float(row["minutes"]),
            float(row["penalties_scored"] + row["penalties_missed"]),
            float(row["own_goals"]),
        ]
        for index, value in enumerate(amounts):
            role_totals[role][index] += value
            player_totals[player_id][index] += value

        if amounts[0] > player_role_minutes.get(player_id, 0):
            player_roles[player_id] = role
            player_role_minutes[player_id] = amounts[0]
    role_priors = {
        role: PlayerEventPrior(penalties / minutes, own_goals / minutes)
        for role, (minutes, penalties, own_goals) in role_totals.items()
    }

    prior_minutes = 1800
    players = {}
    for player_id, (minutes, penalties, own_goals) in player_totals.items():
        prior = role_priors[player_roles[player_id]]
        players[player_id] = PlayerEventPrior(
            (penalties + prior_minutes * prior.penalty_weight) / (minutes + prior_minutes),
            (own_goals + prior_minutes * prior.own_goal_weight) / (minutes + prior_minutes),
        )
    return RareEventPrior(rates, players, role_priors)
