from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from markguardiola.db.models import DataQualityIssue, DataSource, IngestionRun, Match
from markguardiola.ingestion.contracts import CanonicalMatchRecord


def result_provenance(
    source: DataSource, run: IngestionRun, record: CanonicalMatchRecord
) -> dict[str, object]:
    return {
        "source_id": str(source.id),
        "source": source.key,
        "priority": source.priority,
        "ingestion_run_id": str(run.id),
        "source_record_id": record.source_record_id,
        "available_at": record.available_at.isoformat(),
        "policy": "priority_then_recency_v1",
    }


def accept_result(
    session: AsyncSession,
    match: Match,
    source: DataSource,
    run: IngestionRun,
    record: CanonicalMatchRecord,
) -> bool:
    current = (match.home_score, match.away_score)
    incoming = (record.home_score, record.away_score)
    established = all(value is not None for value in current)
    complete = all(value is not None for value in incoming)
    provenance = match.result_provenance or {}
    same_source = provenance.get("source_id") == str(source.id)
    previous_at = datetime.fromisoformat(str(provenance["available_at"])) if provenance else None

    priority = int(str(provenance.get("priority", source.priority)))
    preferred = bool(provenance) and source.priority < priority
    newer = same_source and previous_at is not None and record.available_at >= previous_at
    accepted = not established or (complete and (incoming == current or preferred or newer))
    if match.status in {"awarded", "forfeited"}:
        accepted = incoming == current and record.status == match.status
    if established and complete and incoming != current:
        session.add(
            DataQualityIssue(
                source_id=source.id,
                ingestion_run_id=run.id,
                entity_type="match",
                entity_id=match.id,
                provider_record_id=record.source_record_id,
                rule_key="match.result_conflict",
                severity="warning",
                message="Conflicting result evaluated by provider precedence.",
                evidence={
                    "established": list(current),
                    "incoming": list(incoming),
                    "accepted": accepted,
                    "established_provenance": provenance,
                    "incoming_provenance": result_provenance(source, run, record),
                },
            )
        )
    if accepted and complete and (not provenance or preferred or newer or not established):
        match.result_provenance = result_provenance(source, run, record)
    return accepted
