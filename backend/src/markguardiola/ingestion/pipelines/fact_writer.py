from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from itertools import chain

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from markguardiola.db.models import (
    DataQualityIssue,
    DataSource,
    Event,
    IngestionRun,
    Lineup,
    Match,
    ProviderEntityMap,
    SchemaVersion,
    Shot,
)
from markguardiola.domain.timing import (
    historical_availability_policy,
    historical_result_available_at,
)
from markguardiola.ingestion.contracts.base import CanonicalFixtureFact
from markguardiola.ingestion.identity import fact_id

logger = structlog.get_logger(__name__)
FactTable = type[Lineup] | type[Shot] | type[Event]


class CanonicalFactWriter:
    def __init__(self, session: AsyncSession, *, deterministic_fact_ids: bool = False) -> None:
        self._session = session
        self._deterministic_fact_ids = deterministic_fact_ids

    async def write(
        self,
        *,
        model: FactTable,
        records: Iterable[CanonicalFixtureFact],
        source: DataSource,
        run: IngestionRun,
        schema: SchemaVersion,
    ) -> int:
        iterator = iter(records)
        first = next(iterator, None)
        if first is None:
            return 0
        mappings = (
            await self._session.scalars(
                select(ProviderEntityMap).where(ProviderEntityMap.source_id == source.id)
            )
        ).all()
        identities = {
            (mapping.entity_type, mapping.provider_entity_id): mapping.canonical_entity_id
            for mapping in mappings
        }
        matches = {
            match.id: match
            for match in (
                await self._session.scalars(
                    select(Match).where(
                        Match.id.in_(
                            [
                                canonical
                                for (kind, _), canonical in identities.items()
                                if kind == "match"
                            ]
                        )
                    )
                )
            ).all()
        }
        pending: list[dict[str, object]] = []
        count = rejected = 0
        rejected_examples: list[str] = []
        ingested_at = datetime.now(UTC)
        for record in chain((first,), iterator):
            match_id = identities.get(("match", record.match_provider_id))
            team_id = identities.get(("team", record.team_provider_id or ""))
            player_id = identities.get(("player", record.player_provider_id or ""))
            match = matches.get(match_id) if match_id is not None else None
            invalid = (
                match is None
                or (record.team_provider_id is not None and team_id is None)
                or (record.player_provider_id is not None and player_id is None)
                or (
                    match is not None
                    and team_id is not None
                    and team_id not in {match.home_team_id, match.away_team_id}
                )
            )
            if invalid:
                rejected += 1
                if len(rejected_examples) < 20:
                    rejected_examples.append(record.source_record_id)
                continue
            assert match is not None
            detail = record.model_dump(
                exclude={
                    "source_record_id",
                    "match_provider_id",
                    "team_provider_id",
                    "player_provider_id",
                    "available_at",
                }
            )
            elapsed = (
                detail.get("second")
                if model is Event
                else (int(detail.get("minute") or 0) * 60 if model is Shot else 0)
            )
            event_time = match.kickoff_at + timedelta(seconds=int(elapsed or 0))
            pending.append(
                {
                    "id": fact_id(
                        source.key,
                        model.__tablename__,
                        record.source_record_id,
                        deterministic=self._deterministic_fact_ids,
                    ),
                    "source_id": source.id,
                    "ingestion_run_id": run.id,
                    "schema_version_id": schema.id,
                    "source_record_id": record.source_record_id,
                    "match_id": match.id,
                    "team_id": team_id,
                    "player_id": player_id,
                    "event_time": event_time,
                    "available_at": record.available_at
                    if record.available_at is not None
                    else max(
                        event_time,
                        historical_result_available_at(match.kickoff_at, match.kickoff_precision),
                    ),
                    "ingested_at": ingested_at,
                    "field_provenance": {
                        **{key: source.key for key in detail},
                        "kickoff_precision": match.kickoff_precision,
                        "availability_policy": "observed_response"
                        if record.available_at is not None
                        else historical_availability_policy(match.kickoff_precision),
                    },
                    **detail,
                }
            )
            if len(pending) >= 1000:
                await self._upsert(model, pending)
                count += len(pending)
                pending.clear()
                if count % 100_000 == 0:
                    logger.info("canonical_facts_written", table=model.__tablename__, count=count)
        if pending:
            await self._upsert(model, pending)
            count += len(pending)
        if rejected:
            run.records_rejected += rejected
            self._session.add(
                DataQualityIssue(
                    ingestion_run_id=run.id,
                    source_id=source.id,
                    severity="error",
                    rule_key=f"{model.__tablename__}.unresolved_identity",
                    message="Unresolved or inconsistent entity references were quarantined.",
                    evidence={"count": rejected, "source_record_ids_sample": rejected_examples},
                )
            )
        logger.info(
            "canonical_facts_complete", table=model.__tablename__, count=count, rejected=rejected
        )
        return count

    async def _upsert(self, model: FactTable, records: list[dict[str, object]]) -> None:
        statement = insert(model)
        await self._session.execute(
            statement.on_conflict_do_update(
                index_elements=["source_id", "source_record_id"],
                set_={
                    key: getattr(statement.excluded, key)
                    for key in records[0]
                    if key not in {"id", "source_id", "source_record_id"}
                },
            ),
            records,
        )
