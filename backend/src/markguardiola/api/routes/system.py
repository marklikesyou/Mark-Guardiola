from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from redis.asyncio import Redis
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from markguardiola import __version__
from markguardiola.api.contracts import FreshnessView, SystemStatusView
from markguardiola.api.schemas import HealthResponse, ReadyDependency, ReadyResponse
from markguardiola.api.services.freshness import source_statuses
from markguardiola.core.config import get_settings
from markguardiola.core.time import utcnow
from markguardiola.db.models import (
    BackgroundJob,
    DataQualityIssue,
    IngestionRun,
    Match,
    ModelVersion,
    PredictionRun,
)
from markguardiola.db.session import get_db_session, get_session_factory
from markguardiola.features.pipeline import FEATURE_SCHEMA_VERSION

router = APIRouter(tags=["system"])
Session = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("/health", response_model=HealthResponse, operation_id="health")
async def health() -> HealthResponse:
    return HealthResponse(version=__version__, timestamp=utcnow())


@router.get("/ready", response_model=ReadyResponse, operation_id="ready")
async def ready(response: Response) -> ReadyResponse:
    checks: list[ReadyDependency] = []

    try:
        async with get_session_factory()() as session:
            await session.execute(text("SELECT 1"))
        checks.append(ReadyDependency(name="database", ready=True))
    except Exception:
        checks.append(ReadyDependency(name="database", ready=False))

    settings = get_settings()
    redis = Redis.from_url(settings.redis_url, socket_connect_timeout=1, socket_timeout=1)
    try:
        await redis.ping()
        checks.append(ReadyDependency(name="redis", ready=True))
    except Exception:
        checks.append(ReadyDependency(name="redis", ready=False))
    finally:
        await redis.aclose()

    is_ready = all(check.ready for check in checks)
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadyResponse(
        status="ready" if is_ready else "not_ready",
        dependencies=checks,
        timestamp=utcnow(),
    )


@router.get(
    "/api/v1/system/status",
    response_model=SystemStatusView,
    operation_id="getSystemStatus",
)
async def system_status(session: Session) -> SystemStatusView:
    latest_ingestion = await session.scalar(
        select(func.max(IngestionRun.completed_at)).where(IngestionRun.status == "succeeded")
    )
    latest_prediction = await session.scalar(
        select(func.max(PredictionRun.prediction_cutoff)).where(PredictionRun.status == "succeeded")
    )
    latest_training = await session.scalar(
        select(func.max(ModelVersion.trained_at)).where(ModelVersion.status == "champion")
    )
    unresolved_issues = (
        await session.scalar(
            select(func.count(DataQualityIssue.id)).where(DataQualityIssue.resolved_at.is_(None))
        )
        or 0
    )
    blocking_issues = (
        await session.scalar(
            select(func.count(DataQualityIssue.id)).where(
                DataQualityIssue.resolved_at.is_(None),
                DataQualityIssue.severity == "blocking",
            )
        )
        or 0
    )
    champion_models = (
        await session.scalar(
            select(func.count(ModelVersion.id)).where(ModelVersion.status == "champion")
        )
        or 0
    )
    queued_jobs = (
        await session.scalar(
            select(func.count(BackgroundJob.id)).where(BackgroundJob.status == "queued")
        )
        or 0
    )
    running_jobs = (
        await session.scalar(
            select(func.count(BackgroundJob.id)).where(BackgroundJob.status == "running")
        )
        or 0
    )
    active_model_jobs = (
        await session.scalar(
            select(func.count(BackgroundJob.id)).where(
                BackgroundJob.job_type == "model_training",
                BackgroundJob.status.in_(["queued", "running"]),
            )
        )
        or 0
    )
    warnings: list[str] = []
    notices: list[str] = []
    sources = await source_statuses(session, get_settings())
    api_football = next(source for source in sources if source.key == "api_football")
    if api_football.status != "available":
        notices.append("Infortuni e formazioni ufficiali non sono verificati.")
    if active_model_jobs:
        notices.append("Previsioni in aggiornamento.")
    incompatible = (
        await session.scalar(
            select(func.count(ModelVersion.id)).where(
                ModelVersion.status == "champion",
                ModelVersion.feature_schema_version != FEATURE_SCHEMA_VERSION,
            )
        )
        or 0
    )
    upcoming_count = (
        await session.scalar(
            select(func.count(Match.id)).where(
                Match.kickoff_at > utcnow(),
                Match.kickoff_at < utcnow() + timedelta(days=30),
                Match.status.in_(["fixture", "scheduled"]),
            )
        )
        or 0
    )
    if incompatible and not active_model_jobs:
        warnings.append("I modelli non sono allineati. Rigenera le previsioni.")
    if (
        latest_prediction is not None
        and utcnow() - latest_prediction > timedelta(hours=24)
        and not active_model_jobs
    ):
        warnings.append("Le previsioni hanno più di 24 ore. Aggiorna i dati.")
    if upcoming_count == 0:
        warnings.append(
            "Non ci sono partite in calendario nei prossimi 30 giorni. Aggiorna i dati."
        )
    if latest_ingestion is None:
        warnings.append(
            "Non è stato completato alcun aggiornamento dati. Avvialo da questa pagina."
        )
    if latest_prediction is None:
        warnings.append("Non ci sono previsioni utilizzabili. Rigenerale da questa pagina.")
    if champion_models == 0:
        warnings.append("Non ci sono modelli attivi. Rigenera le previsioni.")
    if blocking_issues:
        warnings.append(
            f"Ci sono {blocking_issues} problemi bloccanti nei dati. Aggiorna i dati e riprova."
        )
    system_state = "degraded" if warnings else "updating" if active_model_jobs else "healthy"
    return SystemStatusView(
        status=system_state,
        freshness=FreshnessView(
            latest_successful_ingestion=latest_ingestion,
            latest_prediction_cutoff=latest_prediction,
            latest_model_training=latest_training,
        ),
        unresolved_quality_issues=unresolved_issues,
        unresolved_blocking_issues=blocking_issues,
        champion_models=champion_models,
        queued_jobs=queued_jobs,
        running_jobs=running_jobs,
        warnings=warnings,
        notices=notices,
        sources=sources,
        incompatible_champion_models=incompatible,
        upcoming_fixture_count=upcoming_count,
    )
