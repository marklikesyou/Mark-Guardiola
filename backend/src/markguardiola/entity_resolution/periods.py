from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from markguardiola.db.models import DataSource, PlayerMatchStat, PlayerTeamPeriod, Transfer
from markguardiola.domain.roles import football_role

POLICY = "observed_membership_spans_v1"


@dataclass(frozen=True, slots=True)
class MembershipObservation:
    player_id: UUID
    team_id: UUID | None
    event_time: datetime
    available_at: datetime
    position: str | None
    source_id: UUID
    ingestion_run_id: UUID
    source_record_id: str
    kind: str


def observed_spans(observations: list[MembershipObservation]) -> list[dict[str, object]]:
    groups: dict[UUID, list[MembershipObservation]] = defaultdict(list)
    for item in observations:
        groups[item.player_id].append(item)
    result: list[dict[str, object]] = []
    for player_id, history in sorted(groups.items()):
        spans: list[list[MembershipObservation]] = []
        for item in sorted(
            history,
            key=lambda row: (
                row.event_time,
                row.available_at,
                row.kind,
                row.source_record_id,
            ),
        ):
            if not spans or spans[-1][-1].team_id != item.team_id:
                spans.append([])
            spans[-1].append(item)
        for span in spans:
            first, last = span[0], span[-1]
            if first.team_id is None:
                continue
            identity = f"{POLICY}:{player_id}:{first.team_id}:{first.event_time.date()}"
            result.append(
                {
                    "id": uuid5(NAMESPACE_URL, identity),
                    "player_id": player_id,
                    "team_id": first.team_id,
                    "valid_from": first.event_time.date(),
                    "valid_to": last.event_time.date(),
                    "position": next(
                        (
                            football_role(row.position)
                            for row in reversed(span)
                            if football_role(row.position)
                        ),
                        None,
                    ),
                    "available_at": max(row.available_at for row in span),
                    "evidence": {
                        "policy": POLICY,
                        "historical_feature_safe": False,
                        "bounds": "first_and_last_observation_not_contract_dates",
                        "observation_count": len(span),
                        "source_ids": sorted({str(row.source_id) for row in span}),
                        "ingestion_run_ids": sorted({str(row.ingestion_run_id) for row in span}),
                        "first": {
                            "source_id": str(first.source_id),
                            "source_record_id": first.source_record_id,
                            "kind": first.kind,
                        },
                        "last": {
                            "source_id": str(last.source_id),
                            "source_record_id": last.source_record_id,
                            "kind": last.kind,
                        },
                    },
                }
            )
    return result


async def materialize_membership_periods(session: AsyncSession) -> int:
    ranked = (
        select(
            PlayerMatchStat.id,
            func.row_number()
            .over(
                partition_by=(PlayerMatchStat.player_id, PlayerMatchStat.match_id),
                order_by=(
                    DataSource.priority,
                    PlayerMatchStat.available_at.desc(),
                    PlayerMatchStat.ingested_at.desc(),
                    PlayerMatchStat.id,
                ),
            )
            .label("rank"),
        )
        .join(DataSource, DataSource.id == PlayerMatchStat.source_id)
        .subquery()
    )
    statement = (
        select(PlayerMatchStat)
        .join(ranked, ranked.c.id == PlayerMatchStat.id)
        .where(ranked.c.rank == 1)
    )
    observations: list[MembershipObservation] = []
    stream = await session.stream_scalars(statement.execution_options(yield_per=2000))
    async for stat in stream:
        observations.append(
            MembershipObservation(
                stat.player_id,
                stat.team_id,
                stat.event_time,
                stat.available_at,
                stat.football_position,
                stat.source_id,
                stat.ingestion_run_id,
                stat.source_record_id,
                "player_match_stat",
            )
        )
    transfers = list(
        await session.scalars(
            select(Transfer).order_by(
                Transfer.available_at,
                Transfer.ingested_at,
                Transfer.id,
            )
        )
    )
    latest = {(row.player_id, row.transfer_date): row for row in transfers}
    for transfer in latest.values():
        observations.append(
            MembershipObservation(
                transfer.player_id,
                transfer.to_team_id,
                datetime.combine(
                    transfer.transfer_date, datetime.min.time(), tzinfo=transfer.available_at.tzinfo
                ),
                transfer.available_at,
                None,
                transfer.source_id,
                transfer.ingestion_run_id,
                transfer.source_record_id,
                "transfer",
            )
        )
    rows = observed_spans(observations)

    await session.execute(
        delete(PlayerTeamPeriod).where(PlayerTeamPeriod.evidence["policy"].as_string() == POLICY)
    )
    for offset in range(0, len(rows), 1000):
        statement_insert = insert(PlayerTeamPeriod).values(rows[offset : offset + 1000])
        await session.execute(
            statement_insert.on_conflict_do_nothing(
                index_elements=["player_id", "team_id", "valid_from"],
            )
        )
    return len(rows)
