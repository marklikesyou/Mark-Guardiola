from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from redis import Redis
from rq import Queue
from sqlalchemy.ext.asyncio import AsyncSession

from markguardiola.api.contracts import JobCreate, JobView
from markguardiola.core.config import get_settings
from markguardiola.core.time import utcnow
from markguardiola.db.models import BackgroundJob
from markguardiola.db.session import get_db_session

router = APIRouter(prefix="/api/v1/admin", tags=["operations"])
Session = Annotated[AsyncSession, Depends(get_db_session)]


@router.post(
    "/data/refresh",
    response_model=JobView,
    status_code=202,
    operation_id="refreshData",
)
async def refresh_data(payload: JobCreate, session: Session) -> JobView:
    return await _enqueue(
        session,
        job_type="data_refresh",
        function="markguardiola.jobs.tasks.run_data_refresh",
        parameters=payload.parameters,
        job_timeout="6h",
    )


@router.post(
    "/models/train",
    response_model=JobView,
    status_code=202,
    operation_id="trainModels",
)
async def train_models(payload: JobCreate, session: Session) -> JobView:
    return await _enqueue(
        session,
        job_type="model_training",
        function="markguardiola.jobs.tasks.run_model_training",
        parameters=payload.parameters,
        job_timeout="12h",
    )


@router.get("/jobs/{job_id}", response_model=JobView, operation_id="getAdminJob")
async def get_job(job_id: uuid.UUID, session: Session) -> JobView:
    job = await session.get(BackgroundJob, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return JobView.model_validate(job)


async def _enqueue(
    session: AsyncSession,
    *,
    job_type: str,
    function: str,
    parameters: dict[str, object],
    job_timeout: str,
) -> JobView:
    job = BackgroundJob(
        job_type=job_type,
        status="queued",
        parameters=parameters,
        progress=0.0,
        queued_at=utcnow(),
    )
    session.add(job)
    await session.commit()
    try:
        redis = Redis.from_url(get_settings().redis_url)
        queued = Queue("markguardiola", connection=redis).enqueue(
            function,
            str(job.id),
            parameters,
            job_timeout=job_timeout,
            result_ttl=86_400,
            failure_ttl=604_800,
        )
        job.queue_job_id = queued.id
        await session.commit()
    except Exception:
        job.status = "failed"
        job.error = "queue_unavailable"
        job.completed_at = utcnow()
        await session.commit()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE) from None
    return JobView.model_validate(job)
