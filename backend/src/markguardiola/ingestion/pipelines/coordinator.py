from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from markguardiola.db.models import (
    DataQualityIssue,
    DataSource,
    IngestionRun,
    RawObject,
    SchemaVersion,
)
from markguardiola.domain.enums import IngestionStatus
from markguardiola.ingestion.contracts import IngestionScope, ProviderAdapter, RawPayload
from markguardiola.ingestion.quality import fingerprint_payload
from markguardiola.ingestion.raw_store import RawObjectStore, StoredRawObject, write_run_manifest

PayloadProcessor = Callable[[DataSource, IngestionRun, SchemaVersion, RawPayload], Awaitable[int]]


class IngestionCoordinator:
    def __init__(self, session: AsyncSession, data_root: Path) -> None:
        self._session = session
        self._raw_store = RawObjectStore(data_root / "raw")
        self._manifest_root = data_root / "manifests"

    async def ingest(
        self,
        adapter: ProviderAdapter,
        scope: IngestionScope,
        *,
        processor: PayloadProcessor | None = None,
    ) -> IngestionRun:
        source = await self._ensure_source(adapter)
        now = datetime.now(UTC)
        run = IngestionRun(
            source_id=source.id,
            status=IngestionStatus.RUNNING,
            started_at=now,
            requested_scope=scope.model_dump(mode="json"),
            records_seen=0,
            records_written=0,
            records_rejected=0,
            manifest={},
        )
        self._session.add(run)
        await self._session.commit()
        run_id = run.id

        stored: list[StoredRawObject] = []
        try:
            async for payload in adapter.iter_raw(scope):
                run.records_seen += 1
                item = self._raw_store.persist(
                    provider=source.key,
                    run_id=str(run.id),
                    payload=payload,
                    competition=scope.competition,
                    season=scope.seasons[-1] if len(scope.seasons) == 1 else None,
                )
                stored.append(item)
                existing = await self._session.scalar(
                    select(RawObject).where(
                        RawObject.source_id == source.id,
                        RawObject.content_sha256 == item.content_sha256,
                    )
                )
                if existing is None:
                    existing = RawObject(
                        source_id=source.id,
                        ingestion_run_id=run.id,
                        schema_version_id=None,
                        provider_object_id=payload.provider_object_id,
                        request_url=payload.request_url,
                        request_params=payload.request_params,
                        storage_path=item.relative_path,
                        media_type=payload.media_type,
                        content_sha256=item.content_sha256,
                        content_bytes=item.content_bytes,
                        event_time=payload.event_time,
                        available_at=payload.available_at,
                        ingested_at=payload.retrieved_at,
                        http_metadata=payload.response_headers,
                    )
                    self._session.add(existing)
                    run.records_written += 1

                await self._session.commit()
                schema_version = await self.resolve_schema(source, payload)
                if existing.schema_version_id is None:
                    existing.schema_version_id = schema_version.id
                if processor is not None:
                    await processor(source, run, schema_version, payload)
                await self._session.commit()

            run.status = IngestionStatus.SUCCEEDED
            if set(scope.data_types).intersection({"player_stats", "transfers", "fixture_details"}):
                from markguardiola.entity_resolution.periods import materialize_membership_periods

                await materialize_membership_periods(self._session)
            run.completed_at = datetime.now(UTC)
            run.manifest = self._write_manifest(str(run.id), stored)
            await self._session.commit()
            return run
        except Exception:
            await self._session.rollback()
            persisted_run = await self._session.get(IngestionRun, run_id)
            if persisted_run is not None:
                persisted_run.status = IngestionStatus.FAILED
                persisted_run.completed_at = datetime.now(UTC)
                persisted_run.error = "ingestion_failed"
                persisted_run.manifest = self._write_manifest(str(run_id), stored)
                self._session.add(
                    DataQualityIssue(
                        source_id=persisted_run.source_id,
                        ingestion_run_id=run_id,
                        rule_key="ingestion.failed",
                        severity="error",
                        message="Ingestion failed. Raw payloads are retained for diagnosis.",
                        evidence={"status": "failed"},
                    )
                )
                await self._session.commit()
            raise

    def _write_manifest(self, run_id: str, stored: list[StoredRawObject]) -> dict[str, object]:
        manifest_path = self._manifest_root / f"ingestion-{run_id}.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        write_run_manifest(manifest_path, stored)
        return {
            "path": str(manifest_path),
            "content_hashes": [item.content_sha256 for item in stored],
        }

    async def _ensure_source(self, adapter: ProviderAdapter) -> DataSource:
        source = await self._session.scalar(select(DataSource).where(DataSource.key == adapter.key))
        if source is None:
            source = DataSource(
                key=adapter.key,
                name=adapter.name,
                base_url=adapter.base_url,
                adapter_version=adapter.adapter_version,
                enabled=True,
                priority=100,
                capabilities={},
                config={},
            )
            self._session.add(source)
            await self._session.flush()
        elif source.adapter_version != adapter.adapter_version:
            source.adapter_version = adapter.adapter_version
        return source

    async def resolve_schema(self, source: DataSource, payload: object) -> SchemaVersion:
        from markguardiola.ingestion.contracts import RawPayload

        if not isinstance(payload, RawPayload):
            raise TypeError()
        fingerprint = fingerprint_payload(payload)
        version = await self._session.scalar(
            select(SchemaVersion).where(
                SchemaVersion.source_id == source.id,
                SchemaVersion.entity_name == fingerprint.version_hint,
                SchemaVersion.fingerprint == fingerprint.digest,
            )
        )
        if version is None:
            version = SchemaVersion(
                source_id=source.id,
                entity_name=fingerprint.version_hint,
                version=fingerprint.digest[:12],
                fingerprint=fingerprint.digest,
                fields={"names": list(fingerprint.fields)},
            )
            self._session.add(version)
            await self._session.flush()
        return version
