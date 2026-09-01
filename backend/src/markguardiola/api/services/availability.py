from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from markguardiola.db.models import Injury, Lineup, Suspension


async def load_unavailable_player_ids(
    session: AsyncSession,
    player_ids: list[UUID],
    cutoff: datetime,
    *,
    fixture_date: date,
    confirmed_at: dict[UUID, datetime] | None = None,
) -> set[UUID]:

    unavailable: set[UUID] = set()
    for model, start, end in (
        (Injury, Injury.started_on, Injury.ended_on),
        (Suspension, Suspension.starts_on, Suspension.ends_on),
    ):
        versions = (
            select(
                model.id,
                func.row_number()
                .over(
                    partition_by=[model.source_id, model.player_id, start],
                    order_by=[model.available_at.desc(), model.ingested_at.desc(), model.id.desc()],
                )
                .label("revision"),
            )
            .where(
                model.player_id.in_(player_ids),
                model.available_at <= cutoff,
            )
            .subquery()
        )
        statement = (
            select(model.player_id, model.available_at)
            .join(versions, versions.c.id == model.id)
            .where(
                versions.c.revision == 1,
                start.is_(None) | (start <= fixture_date),
                end.is_(None) | (end >= fixture_date),
            )
        )
        if model is Injury:
            statement = statement.where(Injury.status.in_(["out", "injured", "unavailable"]))
        unavailable.update(
            player_id
            for player_id, observed in (await session.execute(statement)).all()
            if confirmed_at is None
            or player_id not in confirmed_at
            or observed > confirmed_at[player_id]
        )
    return unavailable


@dataclass(frozen=True, slots=True)
class ConfirmedTeamSheet:
    observed_at: datetime
    starters: frozenset[UUID]
    squad: frozenset[UUID]


async def load_confirmed_lineups(
    session: AsyncSession,
    match_id: UUID,
    cutoff: datetime,
) -> dict[UUID, ConfirmedTeamSheet]:
    rows = (
        await session.scalars(
            select(Lineup)
            .where(Lineup.match_id == match_id, Lineup.available_at <= cutoff)
            .order_by(Lineup.available_at.desc(), Lineup.ingested_at.desc(), Lineup.id)
        )
    ).all()
    snapshots: dict[tuple[UUID, UUID, datetime], list[Lineup]] = {}
    for row in rows:
        snapshots.setdefault((row.team_id, row.source_id, row.available_at), []).append(row)
    output: dict[UUID, ConfirmedTeamSheet] = {}
    seen: set[UUID] = set()
    for (team_id, _source_id, observed), lineup in snapshots.items():
        if team_id in seen:
            continue
        seen.add(team_id)

        starters = frozenset(row.player_id for row in lineup if row.is_starting)
        squad = frozenset(row.player_id for row in lineup)
        if len(starters) == 11 and len(squad) == len(lineup):
            output[team_id] = ConfirmedTeamSheet(observed, starters, squad)
    return output
