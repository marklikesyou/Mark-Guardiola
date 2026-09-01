from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable

from markguardiola.core.config import get_settings
from markguardiola.core.time import utcnow
from markguardiola.db.models import BackgroundJob
from markguardiola.db.session import get_session_factory
from markguardiola.ingestion.pipelines.bootstrap import bootstrap


def run_data_refresh(job_id: str, parameters: dict[str, object]) -> dict[str, object]:
    async def action() -> dict[str, object]:
        first_start_year_value = parameters.get("first_start_year", 2013)
        if isinstance(first_start_year_value, bool) or not isinstance(
            first_start_year_value, (int, str)
        ):
            raise ValueError()
        first_start_year = int(first_start_year_value)
        include_pannadata = bool(parameters.get("include_pannadata", True))
        summary = await bootstrap(
            get_settings(),
            first_start_year=first_start_year,
            include_pannadata=include_pannadata,
        )
        return {
            "ingestion_runs": list(summary.runs),
            "unavailable_enrichments": list(summary.unavailable_enrichments),
        }

    return asyncio.run(_run_tracked(uuid.UUID(job_id), action))


def run_model_training(job_id: str, parameters: dict[str, object]) -> dict[str, object]:
    async def action() -> dict[str, object]:
        from markguardiola.ml.pipeline import rebuild_models
        from markguardiola.ml.training import train_from_snapshot

        if "feature_snapshot_id" in parameters:
            return await train_from_snapshot(parameters)
        return await rebuild_models(parameters)

    return asyncio.run(_run_tracked(uuid.UUID(job_id), action))


async def _run_tracked(
    job_id: uuid.UUID,
    action: Callable[[], Awaitable[dict[str, object]]],
) -> dict[str, object]:
    async with get_session_factory()() as session:
        job = await session.get(BackgroundJob, job_id)
        if job is None:
            raise LookupError()
        job.status = "running"
        job.started_at = utcnow()
        job.progress = 0.05
        await session.commit()
    try:
        result = await action()
    except Exception:
        async with get_session_factory()() as session:
            job = await session.get(BackgroundJob, job_id)
            if job is not None:
                job.status = "failed"
                job.error = "job_failed"
                job.completed_at = utcnow()
                await session.commit()
        raise
    async with get_session_factory()() as session:
        job = await session.get(BackgroundJob, job_id)
        if job is not None:
            job.status = "succeeded"
            job.result = result
            job.progress = 1.0
            job.completed_at = utcnow()
            await session.commit()
    return result
