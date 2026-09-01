from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from markguardiola import __version__
from markguardiola.api.routes.admin import router as admin_router
from markguardiola.api.routes.entities import router as entities_router
from markguardiola.api.routes.leagues import router as leagues_router
from markguardiola.api.routes.player_insights import router as player_insights_router
from markguardiola.api.routes.predictions import router as predictions_router
from markguardiola.api.routes.recommendations import router as recommendations_router
from markguardiola.api.routes.system import router as system_router
from markguardiola.core.config import get_settings
from markguardiola.observability.logging import configure_logging


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    log = structlog.get_logger(__name__)
    log.info("application_started", version=__version__, environment=settings.environment)
    yield
    log.info("application_stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version=__version__,
        description="Probabilistic decision support for Italian Fantacalcio.",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )
    application.include_router(system_router)
    application.include_router(entities_router)
    application.include_router(leagues_router)
    application.include_router(player_insights_router)
    application.include_router(predictions_router)
    application.include_router(recommendations_router)
    application.include_router(admin_router)
    return application


app = create_app()
