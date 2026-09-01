from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from markguardiola.db.models import Shot


@dataclass(frozen=True, slots=True)
class ShotXg:
    attempts: int
    known_xg_attempts: int
    xg: float | None
    available_at: datetime


async def load_shot_xg(
    session: AsyncSession,
    cutoff: datetime | None,
) -> tuple[dict[tuple[UUID, UUID, UUID], ShotXg], set[str]]:
    statement = (
        select(
            Shot.source_id,
            Shot.match_id,
            Shot.player_id,
            func.count(Shot.id),
            func.count(Shot.xg),
            func.sum(Shot.xg),
            func.max(Shot.available_at),
            func.array_agg(func.distinct(Shot.ingestion_run_id)),
        )
        .where(Shot.player_id.is_not(None))
        .group_by(Shot.source_id, Shot.match_id, Shot.player_id)
    )
    if cutoff is not None:
        statement = statement.where(Shot.available_at <= cutoff, Shot.event_time < cutoff)
    summaries: dict[tuple[UUID, UUID, UUID], ShotXg] = {}
    runs: set[str] = set()
    for (
        source,
        match,
        player,
        attempts,
        known,
        xg,
        available,
        ingestion_ids,
    ) in await session.execute(statement):
        summaries[(source, match, player)] = ShotXg(attempts, known, xg, available)
        runs.update(str(identifier) for identifier in ingestion_ids)
    return summaries, runs


def covered_xg(attempts: float | None, shots: ShotXg | None) -> float | None:

    if attempts == 0 and (shots is None or shots.attempts == 0):
        return 0.0
    if shots is not None and attempts == shots.attempts == shots.known_xg_attempts:
        return shots.xg
    return None
