from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from markguardiola.core.config import Settings
from markguardiola.db.base import Base
from markguardiola.db.models import DataQualityIssue, DataSource, IngestionRun, SchemaVersion
from markguardiola.db.session import get_session_factory
from markguardiola.entity_resolution.periods import materialize_membership_periods
from markguardiola.entity_resolution.reconcile import reconcile_identities
from markguardiola.ingestion.adapters.api_football_parser import parse_api_football
from markguardiola.ingestion.adapters.football_data_co_uk import FootballDataCoUkAdapter
from markguardiola.ingestion.adapters.football_data_org_parser import parse_football_data_org
from markguardiola.ingestion.adapters.soccerdata_optional import PROVIDERS as BRONZE_ONLY_PROVIDERS
from markguardiola.ingestion.adapters.understat_parser import parse_team_matches
from markguardiola.ingestion.contracts import IngestionScope, RawPayload
from markguardiola.ingestion.pipelines.canonical_writer import CanonicalWriter
from markguardiola.ingestion.pipelines.coordinator import IngestionCoordinator, PayloadProcessor
from markguardiola.ingestion.pipelines.fact_writer import CanonicalFactWriter
from markguardiola.ingestion.pipelines.operational import OperationalProcessor
from markguardiola.ingestion.pipelines.processors import PannadataProcessor, UnderstatProcessor
from markguardiola.ml.registry.artifacts import archive_source_code
from markguardiola.release.manifest import BLOCK_SIZE, RAW_INPUT_TABLES, BundleManifest, safe_path


@dataclass(frozen=True, slots=True)
class ArchivedObservation:
    path: Path
    envelope: dict[str, Any]
    sha256: str
    identity: str

    def read(self) -> RawPayload:
        content = self.path.read_bytes()
        if hashlib.sha256(content).hexdigest() != self.sha256:
            raise ValueError()
        if len(content) != self.envelope["content_bytes"]:
            raise ValueError()
        return RawPayload.model_validate({**self.envelope, "content": content})


@dataclass(frozen=True, slots=True)
class ArchivedRun:
    source: DataSource
    original: IngestionRun
    scope: IngestionScope
    observations: tuple[ArchivedObservation, ...]


def _read_json(path: Path) -> dict[str, Any]:
    if path.stat().st_size > 16 * BLOCK_SIZE:
        raise ValueError()
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError()
    return value


def _safe_file(root: Path, relative: str) -> Path:
    safe_path(relative)
    path = root / relative
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError()
    return path


def _run_manifest(data_root: Path, manifest_path: str) -> dict[str, Any]:
    relative = Path(manifest_path).resolve().relative_to(data_root.resolve()).as_posix()
    return _read_json(_safe_file(data_root, relative))


def _priority(observation: ArchivedObservation) -> tuple[int, str, str]:
    hint = str(observation.envelope.get("schema_hint", "")).casefold()
    priorities = (
        ("manifest", 0),
        ("github-release", 0),
        ("original-response", 0),
        ("fixture", 1),
        ("schedule", 1),
        ("player", 2),
        ("team_match", 2),
        ("lineup", 3),
        ("shot", 4),
        ("event", 5),
    )
    priority = next((rank for token, rank in priorities if token in hint), 6)
    return priority, str(observation.envelope.get("provider_object_id", "")), observation.sha256


async def _plan(
    session: AsyncSession, settings: Settings
) -> tuple[list[ArchivedRun], dict[str, Any]]:
    rows = (
        await session.execute(
            select(IngestionRun, DataSource)
            .join(DataSource, DataSource.id == IngestionRun.source_id)
            .order_by(IngestionRun.started_at, IngestionRun.id)
        )
    ).all()
    result: list[ArchivedRun] = []
    seen: set[str] = set()
    duplicates = 0
    bronze_only: set[str] = set()
    unavailable: list[str] = []
    for original, source in rows:
        if original.manifest.get("replay_of"):
            continue
        if source.key in BRONZE_ONLY_PROVIDERS:
            bronze_only.add(source.key)
            continue
        if source.key not in {
            "football_data_co_uk",
            "pannadata",
            "understat",
            "api_football",
            "football_data_org",
        }:
            raise ValueError()
        if original.status != "succeeded":
            unavailable.append(str(original.id))
            continue
        raw_manifest_path = original.manifest.get("path")
        if not isinstance(raw_manifest_path, str):
            raise ValueError()
        raw_manifest = await asyncio.to_thread(_run_manifest, settings.data_root, raw_manifest_path)
        scope = IngestionScope.model_validate(original.requested_scope)
        observations: list[ArchivedObservation] = []
        for entry in raw_manifest.get("objects", []):
            path = _safe_file(settings.data_root / "raw", entry["relative_path"])
            envelope = _read_json(
                _safe_file(settings.data_root / "raw", f"{entry['relative_path']}.metadata.json")
            )
            if entry["content_sha256"] != envelope.get("content_sha256"):
                raise ValueError()
            identity = hashlib.sha256(
                json.dumps(
                    {
                        "source": source.key,
                        "scope": scope.model_dump(mode="json"),
                        "envelope": envelope,
                    },
                    sort_keys=True,
                ).encode()
            ).hexdigest()
            if identity in seen:
                duplicates += 1
                continue
            seen.add(identity)
            observations.append(
                ArchivedObservation(path, envelope, entry["content_sha256"], identity)
            )
        if observations:
            result.append(
                ArchivedRun(source, original, scope, tuple(sorted(observations, key=_priority)))
            )
    if not result:
        raise ValueError()
    result, quarantined = await asyncio.to_thread(_validate_understat_archives, result)
    return result, {
        "duplicate_immutable_observations": duplicates,
        "bronze_only_sources": sorted(bronze_only),
        "failed_or_unfinished_input_runs": unavailable,
        "quarantined_observations": quarantined,
    }


def _validate_understat_archives(
    runs: list[ArchivedRun],
) -> tuple[list[ArchivedRun], list[dict[str, Any]]]:

    valid: dict[str, list[tuple[ArchivedRun, ArchivedObservation]]] = {}
    invalid: list[tuple[str, ArchivedRun, ArchivedObservation]] = []
    for run in runs:
        if run.source.key != "understat":
            continue
        for observation in run.observations:
            payload = observation.read()
            if payload.schema_hint not in {
                "soccerdata-understat:team_match_stats",
                "soccerdata-understat:schedule",
            }:
                continue
            request = json.dumps(
                {
                    "scope": run.scope.model_dump(mode="json"),
                    "schema": payload.schema_hint,
                    "url": payload.request_url,
                    "params": payload.request_params,
                    "provider_object_id": payload.provider_object_id,
                },
                sort_keys=True,
            )
            try:
                records = parse_team_matches(payload)
            except ValueError:
                invalid.append((request, run, observation))
            else:
                if records:
                    valid.setdefault(request, []).append((run, observation))
    quarantined: set[str] = set()
    report: list[dict[str, Any]] = []
    for request, run, observation in invalid:
        replacement = next(
            (
                (candidate, raw)
                for candidate, raw in valid.get(request, [])
                if candidate.original.started_at > run.original.started_at
            ),
            None,
        )
        if replacement is None:
            raise ValueError()
        candidate, raw = replacement
        quarantined.add(observation.identity)
        report.append(
            {
                "source": run.source.key,
                "input_run_id": str(run.original.id),
                "raw_sha256": observation.sha256,
                "reason": "invalid_payload",
                "replacement_run_id": str(candidate.original.id),
                "replacement_raw_sha256": raw.sha256,
            }
        )
    return (
        [
            replace(
                run,
                observations=tuple(
                    item for item in run.observations if item.identity not in quarantined
                ),
            )
            for run in runs
        ],
        report,
    )


def _processor(
    session: AsyncSession, source: str, scope: IngestionScope, as_of: datetime
) -> PayloadProcessor:
    writer = CanonicalWriter(session, as_of=as_of, deterministic_fact_ids=True)
    facts = CanonicalFactWriter(session, deterministic_fact_ids=True)
    if source == "football_data_co_uk":

        async def football_data(
            source: DataSource, run: IngestionRun, schema: SchemaVersion, payload: RawPayload
        ) -> int:
            return await writer.write_matches(
                source=source,
                run=run,
                schema_version=schema,
                records=FootballDataCoUkAdapter.parse_matches(payload),
            )

        return football_data
    if source == "pannadata":
        return PannadataProcessor(scope, writer, facts)
    if source == "understat":
        return UnderstatProcessor(writer)
    parser = {"api_football": parse_api_football, "football_data_org": parse_football_data_org}.get(
        source
    )
    if parser is None:
        raise ValueError()
    return OperationalProcessor(
        session, parser, writer=writer, facts=facts, deterministic_fact_ids=True
    )


async def replay_raw_inputs(
    settings: Settings, manifest: BundleManifest, *, bundle_sha256: str
) -> dict[str, Any]:
    as_of = manifest.replay_cutoff
    async with get_session_factory()() as session:
        for table in Base.metadata.sorted_tables:
            if table.name not in RAW_INPUT_TABLES and await session.scalar(
                select(table.c.id).limit(1)
            ):
                raise ValueError()
        plan, report = await _plan(session, settings)
        revision = archive_source_code(settings.artifact_root)
        replayed: list[str] = []
        canonical_records_processed = 0
        for input_run in plan:
            rejected = [
                item
                for item in report["quarantined_observations"]
                if item["input_run_id"] == str(input_run.original.id)
            ]
            run_id = uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"markguardiola:replay:v1:{bundle_sha256}:{revision}:{input_run.original.id}",
            )
            run = IngestionRun(
                id=run_id,
                source_id=input_run.source.id,
                status="running",
                started_at=datetime.now(UTC),
                requested_scope=input_run.scope.model_dump(mode="json"),
                code_revision=revision,
                records_seen=len(rejected),
                records_written=0,
                records_rejected=len(rejected),
                manifest={
                    **input_run.original.manifest,
                    "replay_of": str(input_run.original.id),
                    "bundle_sha256": bundle_sha256,
                    "archive_cutoff": as_of.isoformat(),
                    "quarantined_observations": rejected,
                },
            )
            session.add(run)
            await session.flush()
            for rejection in rejected:
                session.add(
                    DataQualityIssue(
                        source_id=input_run.source.id,
                        ingestion_run_id=run_id,
                        rule_key="raw_replay.superseded_invalid_observation",
                        severity="warning",
                        message=(
                            "Archived observation failed current validation; a later validated "
                            "response to the same request is replayed. Original raw bytes retained."
                        ),
                        evidence=rejection,
                    )
                )
            await session.commit()
            process = _processor(session, input_run.source.key, input_run.scope, as_of)
            coordinator = IngestionCoordinator(session, settings.data_root)
            try:
                for observation in input_run.observations:
                    payload = await asyncio.to_thread(observation.read)
                    schema = await coordinator.resolve_schema(input_run.source, payload)
                    canonical_records_processed += await process(
                        input_run.source, run, schema, payload
                    )
                    run.records_written += 1
                    run.records_seen += 1
                    await session.commit()
                    print(
                        f"Replayed {input_run.source.key}: {payload.schema_hint} "
                        f"({run.records_seen}/{len(input_run.observations) + len(rejected)})",
                        flush=True,
                    )
                run.status = "succeeded"
                run.completed_at = datetime.now(UTC)
                await session.commit()
                replayed.append(str(run_id))
            except Exception:
                await session.rollback()
                persisted = await session.get_one(IngestionRun, run_id)
                persisted.status = "failed"
                persisted.completed_at = datetime.now(UTC)
                persisted.error = "replay_failed"
                await session.commit()
                raise
        await reconcile_identities(session, apply=True)
        memberships = await materialize_membership_periods(session)
        await session.commit()
    result = {
        **report,
        "status": "rebuilt",
        "archive_version": manifest.version,
        "archive_cutoff": as_of.isoformat(),
        "bundle_sha256": bundle_sha256,
        "processor_revision": revision,
        "replay_runs": replayed,
        "materialized_memberships": memberships,
        "canonical_records_processed": canonical_records_processed,
    }
    report_path = settings.data_root / "manifests" / f"raw-rebuild-{bundle_sha256}.json"
    with report_path.open("x", encoding="utf-8") as output:
        json.dump(result, output, indent=2, sort_keys=True)
    return result
