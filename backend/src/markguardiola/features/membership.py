from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from markguardiola.db.models import Lineup, Match, Player, Transfer
from markguardiola.domain.roles import football_role


@dataclass(frozen=True, slots=True)
class UpcomingMemberships:
    by_fixture_team: dict[tuple[UUID, UUID], list[tuple[UUID, str]]]
    ingestion_run_ids: tuple[str, ...]
    available_at: dict[tuple[UUID, UUID], datetime]


async def resolve_upcoming_memberships(
    session: AsyncSession,
    matches: list[Match],
    cutoff: datetime,
    historical: dict[UUID, tuple[datetime, UUID, str]],
    historical_available_at: dict[UUID, datetime],
) -> UpcomingMemberships:
    transfers = (
        await session.execute(
            select(Transfer, Player)
            .join(Player, Player.id == Transfer.player_id)
            .where(Transfer.available_at <= cutoff)
            .order_by(
                Transfer.transfer_date, Transfer.available_at, Transfer.ingested_at, Transfer.id
            )
        )
    ).all()
    lineups = (
        await session.scalars(
            select(Lineup)
            .where(
                Lineup.match_id.in_([match.id for match in matches]), Lineup.available_at <= cutoff
            )
            .order_by(Lineup.available_at, Lineup.ingested_at, Lineup.id)
        )
    ).all()
    by_fixture_team: dict[tuple[UUID, UUID], list[tuple[UUID, str]]] = {}
    runs: set[str] = set()
    available_at: dict[tuple[UUID, UUID], datetime] = {}
    for match in matches:
        membership = {
            player_id: observation
            for player_id, observation in historical.items()
            if observation[0].date() >= (cutoff - timedelta(days=365)).date()
        }
        observed_at = dict(historical_available_at)
        for transfer, player in transfers:
            previous = membership.get(player.id) or historical.get(player.id)
            if transfer.transfer_date > match.kickoff_at.date() or (
                previous is not None and transfer.transfer_date < previous[0].date()
            ):
                continue
            role = (
                previous[2]
                if previous is not None
                else (
                    football_role(player.primary_position) if player.updated_at <= cutoff else None
                )
            )
            if transfer.to_team_id is None:
                membership.pop(player.id, None)
            elif role is not None:
                effective = datetime.combine(
                    transfer.transfer_date, datetime.min.time(), tzinfo=cutoff.tzinfo
                )
                membership[player.id] = (effective, transfer.to_team_id, role)
                observed_at[player.id] = transfer.available_at
            runs.add(str(transfer.ingestion_run_id))
        for lineup in lineups:
            if lineup.match_id != match.id:
                continue
            previous = membership.get(lineup.player_id)
            role = football_role(lineup.position) or (previous[2] if previous else None)
            if role is not None:
                membership[lineup.player_id] = (lineup.event_time, lineup.team_id, role)
                observed_at[lineup.player_id] = lineup.available_at
                runs.add(str(lineup.ingestion_run_id))
        for team_id in (match.home_team_id, match.away_team_id):
            by_fixture_team[(match.id, team_id)] = sorted(
                [
                    (player_id, role)
                    for player_id, (_, club, role) in membership.items()
                    if club == team_id
                ],
                key=lambda item: item[0],
            )
            for player_id, _role in by_fixture_team[(match.id, team_id)]:
                available_at[(match.id, player_id)] = observed_at[player_id]
    return UpcomingMemberships(by_fixture_team, tuple(sorted(runs)), available_at)
