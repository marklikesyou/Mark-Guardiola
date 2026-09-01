from __future__ import annotations

import math
import uuid
from collections import defaultdict
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from markguardiola.api.contracts import (
    PlayerFormMatch,
    PlayerRecentFormView,
    PlayerStatProvenance,
)
from markguardiola.api.services.views import team_summary
from markguardiola.db.models import DataSource, Match, PlayerMatchStat, Team
from markguardiola.domain.enums import KickoffPrecision

_METRICS = {
    "goals": ("goals", "goals_scored"),
    "assists": ("assists", "goal_assist"),
    "shots": ("shots", "total_scoring_att"),
    "xg": ("xg", "expected_goals"),
    "xa": ("xa", "expected_assists"),
    "base_rating": ("base_rating", "rating"),
}
_COUNTS = {"goals", "assists", "shots"}


async def load_recent_form(
    session: AsyncSession, *, player_id: uuid.UUID, as_of: datetime, limit: int
) -> PlayerRecentFormView:
    eligibility = (
        PlayerMatchStat.player_id == player_id,
        PlayerMatchStat.available_at <= as_of,
        PlayerMatchStat.event_time < as_of,
        or_(
            PlayerMatchStat.team_id == Match.home_team_id,
            PlayerMatchStat.team_id == Match.away_team_id,
        ),
    )

    match_ids = (
        select(Match.id)
        .join(PlayerMatchStat, PlayerMatchStat.match_id == Match.id)
        .where(*eligibility, Match.kickoff_at < as_of, Match.status == "finished")
        .group_by(Match.id, Match.kickoff_at)
        .order_by(Match.kickoff_at.desc(), Match.id)
        .limit(limit)
    )
    rows = (
        await session.execute(
            select(PlayerMatchStat, DataSource, Match)
            .join(DataSource, DataSource.id == PlayerMatchStat.source_id)
            .join(Match, Match.id == PlayerMatchStat.match_id)
            .where(*eligibility, Match.id.in_(match_ids))
            .order_by(
                Match.kickoff_at.desc(),
                Match.id,
                DataSource.priority,
                DataSource.key,
                PlayerMatchStat.available_at.desc(),
                PlayerMatchStat.ingested_at.desc(),
                PlayerMatchStat.id,
            )
        )
    ).all()
    grouped: dict[uuid.UUID, list[tuple[PlayerMatchStat, DataSource]]] = defaultdict(list)
    matches: dict[uuid.UUID, Match] = {}
    for stat, source, match in rows:
        grouped[match.id].append((stat, source))
        matches[match.id] = match
    team_ids = {
        team for match in matches.values() for team in (match.home_team_id, match.away_team_id)
    }
    teams = {
        team.id: team
        for team in (await session.scalars(select(Team).where(Team.id.in_(team_ids)))).all()
    }
    warnings: set[str] = set()
    items = [
        _form_match(matches[match_id], observations, teams, warnings)
        for match_id, observations in grouped.items()
    ]
    if not items:
        warnings.add("Nessuna prestazione osservata disponibile entro la data richiesta.")
    if any(getattr(item, metric) is None for item in items for metric in _METRICS):
        warnings.add("Alcune statistiche non sono disponibili: non vengono sostituite con zeri.")
    return PlayerRecentFormView(
        player_id=player_id,
        as_of=as_of,
        data_cutoff=max(
            (source.available_at for item in items for source in item.sources), default=None
        ),
        limit=limit,
        items=items,
        warnings=tuple(sorted(warnings)),
    )


def _form_match(
    match: Match,
    observations: list[tuple[PlayerMatchStat, DataSource]],
    teams: dict[uuid.UUID, Team],
    warnings: set[str],
) -> PlayerFormMatch:
    primary, _ = observations[0]
    fields = {key: primary.id for key in ("team", "minutes", "started")}
    selected: dict[str, float | None] = dict.fromkeys(_METRICS)
    for stat, _source in observations:
        if stat.team_id != primary.team_id:
            warnings.add("Fonti discordanti sulla squadra: applicata la priorità delle fonti.")
            continue
        for metric, aliases in _METRICS.items():
            value = _metric_value(stat.stats, metric, aliases)
            if value is None:
                continue
            if metric not in fields:
                selected[metric] = value
                fields[metric] = stat.id
            elif selected[metric] != value:
                warnings.add(
                    "Statistiche discordanti: applicate priorità delle fonti "
                    "e data di pubblicazione."
                )
    used = set(fields.values())
    is_home = primary.team_id == match.home_team_id

    return PlayerFormMatch(
        match_id=match.id,
        kickoff_at=match.kickoff_at,
        kickoff_precision=KickoffPrecision(match.kickoff_precision or "unknown"),
        matchweek=match.matchweek,
        team=team_summary(teams[primary.team_id]),
        opponent=team_summary(teams[match.away_team_id if is_home else match.home_team_id]),
        is_home=is_home,
        minutes=primary.minutes,
        started=primary.started,
        goals=_count(selected["goals"]),
        assists=_count(selected["assists"]),
        shots=_count(selected["shots"]),
        xg=selected["xg"],
        xa=selected["xa"],
        base_rating=selected["base_rating"],
        field_sources=fields,
        sources=[_provenance(stat, source) for stat, source in observations if stat.id in used],
    )


def _count(value: float | None) -> int | None:
    return int(value) if value is not None else None


def _metric_value(values: dict[str, object], metric: str, aliases: tuple[str, ...]) -> float | None:
    if metric in _COUNTS and not values.get("event_statistics_available", 1):
        return None
    for key in aliases:
        raw = values.get(key)
        if isinstance(raw, bool) or not isinstance(raw, (str, int, float)):
            continue
        try:
            value = float(raw)
        except ValueError:
            continue
        if not math.isfinite(value) or value < 0:
            continue
        if metric in _COUNTS and not value.is_integer():
            continue
        if metric == "base_rating" and value > 10:
            continue
        return value

    if metric in _COUNTS and not any(key in values for key in aliases):
        return 0.0
    return None


def _provenance(stat: PlayerMatchStat, source: DataSource) -> PlayerStatProvenance:
    return PlayerStatProvenance(
        stat_id=stat.id,
        source_id=source.id,
        source_key=source.key,
        source_name=source.name,
        source_priority=source.priority,
        source_record_id=stat.source_record_id,
        ingestion_run_id=stat.ingestion_run_id,
        schema_version_id=stat.schema_version_id,
        adapter_version=source.adapter_version,
        event_time=stat.event_time,
        available_at=stat.available_at,
        ingested_at=stat.ingested_at,
        field_provenance=stat.field_provenance,
    )
