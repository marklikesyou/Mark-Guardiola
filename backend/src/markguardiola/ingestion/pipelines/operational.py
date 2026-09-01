from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from markguardiola.db.models import (
    DataSource,
    Event,
    IngestionRun,
    Injury,
    Lineup,
    OddsSnapshot,
    SchemaVersion,
    Season,
    Suspension,
    TeamStandingSnapshot,
    Transfer,
)
from markguardiola.domain.enums import EntityType
from markguardiola.ingestion.contracts import RawPayload
from markguardiola.ingestion.contracts.operational import OperationalBatch, OperationalObservation
from markguardiola.ingestion.identity import fact_id
from markguardiola.ingestion.pipelines.canonical_writer import (
    BlockingDataQualityError,
    CanonicalWriter,
)
from markguardiola.ingestion.pipelines.fact_writer import CanonicalFactWriter


class OperationalProcessor:
    def __init__(
        self,
        session: AsyncSession,
        parser: Callable[[RawPayload], OperationalBatch],
        *,
        writer: CanonicalWriter | None = None,
        facts: CanonicalFactWriter | None = None,
        deterministic_fact_ids: bool = False,
    ) -> None:
        self._session = session
        self._parser = parser
        self._deterministic_fact_ids = deterministic_fact_ids
        self._writer = writer if writer is not None else CanonicalWriter(session)
        self._facts = facts if facts is not None else CanonicalFactWriter(session)

    async def __call__(
        self, source: DataSource, run: IngestionRun, schema: SchemaVersion, payload: RawPayload
    ) -> int:
        batch = self._parser(payload)
        count = (
            await self._writer.write_matches(
                source=source, run=run, records=batch.matches, schema_version=schema
            )
            if batch.matches
            else 0
        )
        for team in batch.teams:
            await self._writer.resolve_team(
                source, team.provider_id, team.name, payload.retrieved_at
            )
        count += await self._writer.write_player_identities(
            source, run, batch.players, schema_version=schema
        )
        count += (
            await self._writer.write_player_matches(
                source=source, run=run, schema_version=schema, records=batch.player_stats
            )
            if batch.player_stats
            else 0
        )
        await self._session.flush()
        for model, records in ((Lineup, batch.lineups), (Event, batch.events)):
            count += await self._facts.write(
                model=model, records=records, source=source, run=run, schema=schema
            )
        for absence in batch.availability:
            values = self._provenance(source, run, schema, absence)
            values.update(
                player_id=await self._writer.resolve_mapping(
                    source, EntityType.PLAYER, absence.player_provider_id
                ),
                team_id=await self._writer.resolve_mapping(
                    source, EntityType.TEAM, absence.team_provider_id
                ),
            )
            if absence.suspended:
                values.update(
                    reason=absence.reason, starts_on=absence.starts_on, ends_on=absence.ends_on
                )
                await self._insert(Suspension, values)
            else:
                values.update(
                    injury_type=absence.reason,
                    status=absence.status,
                    started_on=absence.starts_on,
                    ended_on=absence.ends_on,
                )
                await self._insert(Injury, values)
            count += 1
        for transfer in batch.transfers:
            values = self._provenance(source, run, schema, transfer)
            values.update(
                player_id=await self._writer.resolve_mapping(
                    source, EntityType.PLAYER, transfer.player_provider_id
                ),
                transfer_date=transfer.transfer_date,
                transfer_type=transfer.transfer_type,
            )
            for key, transfer_team in (
                ("from_team_id", transfer.from_team),
                ("to_team_id", transfer.to_team),
            ):
                values[key] = (
                    (
                        await self._writer.resolve_team(
                            source,
                            transfer_team.provider_id,
                            transfer_team.name,
                            transfer.available_at,
                        )
                    ).id
                    if transfer_team
                    else None
                )
            await self._insert(Transfer, values)
            count += 1
        for standing in batch.standings:
            season = await self._session.scalar(
                select(Season).where(Season.label == standing.season_label)
            )
            if season is None:
                raise BlockingDataQualityError()
            standing_team = await self._writer.resolve_team(
                source, standing.team.provider_id, standing.team.name, standing.available_at
            )
            values = self._provenance(source, run, schema, standing)
            values.update(
                standing.model_dump(
                    exclude={
                        "team",
                        "season_label",
                        "source_record_id",
                        "event_time",
                        "available_at",
                    }
                )
            )
            values.update(team_id=standing_team.id, season_id=season.id)
            await self._insert(TeamStandingSnapshot, values)
            count += 1
        for odds in batch.odds:
            values = self._provenance(source, run, schema, odds)
            values.update(
                match_id=await self._writer.resolve_mapping(
                    source, EntityType.MATCH, odds.match_provider_id
                ),
                bookmaker=odds.bookmaker,
                market=odds.market,
                selection=odds.selection,
                decimal_odds=Decimal(str(odds.decimal_odds)),
            )
            await self._insert(OddsSnapshot, values)
            count += 1
        return count

    @staticmethod
    def _provenance(
        source: DataSource, run: IngestionRun, schema: SchemaVersion, record: OperationalObservation
    ) -> dict[str, object]:
        return {
            "source_id": source.id,
            "ingestion_run_id": run.id,
            "schema_version_id": schema.id,
            "source_record_id": record.source_record_id,
            "event_time": record.event_time,
            "available_at": record.available_at,
            "ingested_at": datetime.now(UTC),
            "field_provenance": {
                **{key: source.key for key in record.model_fields_set},
                "availability_policy": "observed_response",
            },
        }

    async def _insert(
        self,
        model: type[Injury]
        | type[Suspension]
        | type[Transfer]
        | type[TeamStandingSnapshot]
        | type[OddsSnapshot],
        values: dict[str, object],
    ) -> None:
        if self._deterministic_fact_ids:
            values = {
                **values,
                "id": fact_id(
                    str(values["source_id"]),
                    model.__tablename__,
                    str(values["source_record_id"]),
                    deterministic=True,
                ),
            }
        await self._session.execute(
            insert(model)
            .values(**values)
            .on_conflict_do_nothing(index_elements=["source_id", "source_record_id"])
        )
