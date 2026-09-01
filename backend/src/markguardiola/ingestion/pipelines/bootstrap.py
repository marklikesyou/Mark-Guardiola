from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import structlog

from markguardiola.core.config import Settings
from markguardiola.db.session import get_session_factory
from markguardiola.ingestion.adapters import (
    ApiFootballAdapter,
    FootballDataCoUkAdapter,
    PannadataAdapter,
    UnderstatAdapter,
)
from markguardiola.ingestion.adapters.api_football_parser import parse_api_football
from markguardiola.ingestion.adapters.football_data_org import FootballDataOrgAdapter
from markguardiola.ingestion.adapters.football_data_org_parser import parse_football_data_org
from markguardiola.ingestion.adapters.http import FileResponseCache, HttpAdapterClient
from markguardiola.ingestion.contracts import IngestionScope
from markguardiola.ingestion.pipelines.canonical_writer import CanonicalWriter
from markguardiola.ingestion.pipelines.coordinator import IngestionCoordinator
from markguardiola.ingestion.pipelines.fact_writer import CanonicalFactWriter
from markguardiola.ingestion.pipelines.operational import OperationalProcessor
from markguardiola.ingestion.pipelines.processors import (
    FootballDataCoUkProcessor,
    PannadataProcessor,
    UnderstatProcessor,
)

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class BootstrapSummary:
    runs: tuple[str, ...]
    unavailable_enrichments: tuple[str, ...]


def current_season_label(now: datetime | None = None) -> str:
    point = now or datetime.now(UTC)
    start = point.year if point.month >= 7 else point.year - 1
    return f"{start:04d}-{start + 1:04d}"


def historical_seasons(first_start_year: int, last_label: str) -> tuple[str, ...]:
    last_start = int(last_label[:4])
    if first_start_year > last_start:
        raise ValueError()
    return tuple(f"{year:04d}-{year + 1:04d}" for year in range(first_start_year, last_start + 1))


async def bootstrap(
    settings: Settings,
    *,
    first_start_year: int = 2013,
    include_pannadata: bool = True,
    include_understat: bool = True,
    pannadata_types: tuple[str, ...] = ("fixtures", "player_stats", "lineups", "shots", "events"),
) -> BootstrapSummary:
    season = current_season_label()
    seasons = historical_seasons(first_start_year, season)
    data_root = settings.data_root
    cache = FileResponseCache(data_root / "raw" / ".http-cache")
    client = HttpAdapterClient(cache=cache)
    run_ids: list[str] = []
    unavailable: list[str] = []

    async with get_session_factory()() as session:
        coordinator = IngestionCoordinator(session, data_root)
        writer = CanonicalWriter(session)

        historical_adapter = FootballDataCoUkAdapter(client)
        historical_scope = IngestionScope(seasons=seasons, data_types=("matches", "odds"))
        historical_run = await coordinator.ingest(
            historical_adapter,
            historical_scope,
            processor=FootballDataCoUkProcessor(historical_adapter, writer),
        )
        run_ids.append(str(historical_run.id))

        if include_pannadata:
            pannadata_scope = IngestionScope(
                seasons=seasons,
                data_types=pannadata_types,
            )
            pannadata_run = await coordinator.ingest(
                PannadataAdapter(client),
                pannadata_scope,
                processor=PannadataProcessor(pannadata_scope, writer, CanonicalFactWriter(session)),
            )
            run_ids.append(str(pannadata_run.id))

        if include_understat:
            for label in seasons:
                if int(label[:4]) < 2014:
                    continue
                try:
                    understat_run = await coordinator.ingest(
                        UnderstatAdapter(cache_dir=data_root / "raw" / ".soccerdata" / "Understat"),
                        IngestionScope(
                            seasons=(label,),
                            data_types=("schedule", "team_match_stats")
                            if label == season
                            else ("team_match_stats",),
                        ),
                        processor=UnderstatProcessor(CanonicalWriter(session)),
                    )
                    run_ids.append(str(understat_run.id))
                except Exception:
                    unavailable.append(f"understat:{label}")
                    logger.warning(
                        "optional_enrichment_unavailable",
                        source="understat",
                        season=label,
                    )

        if settings.api_football_key is not None:
            current_scope = IngestionScope(
                seasons=(season,),
                data_types=(
                    "fixtures",
                    "fixture_details",
                    "injuries",
                    "teams",
                    "players",
                    "standings",
                    "odds",
                    "transfers",
                ),
            )
            try:
                current_run = await coordinator.ingest(
                    ApiFootballAdapter(
                        client,
                        settings.api_football_key,
                        daily_limit=settings.api_football_daily_limit,
                        quota_ledger=data_root / "raw" / ".quota" / "api-football.sqlite3",
                    ),
                    current_scope,
                    processor=OperationalProcessor(session, parse_api_football),
                )
                run_ids.append(str(current_run.id))
            except Exception:
                unavailable.append("api_football_current_lineups_injuries_events")
                logger.warning(
                    "optional_enrichment_unavailable",
                    source="api_football",
                )
        else:
            unavailable.append("api_football_current_lineups_injuries_events")

        if settings.football_data_org_key is not None:
            try:
                fallback_run = await coordinator.ingest(
                    FootballDataOrgAdapter(client, settings.football_data_org_key),
                    IngestionScope(seasons=(season,), data_types=("matches", "standings", "teams")),
                    processor=OperationalProcessor(session, parse_football_data_org),
                )
                run_ids.append(str(fallback_run.id))
            except Exception:
                unavailable.append("football_data_org_schedule_standings")
                logger.warning(
                    "optional_enrichment_unavailable",
                    source="football_data_org",
                )
        else:
            unavailable.append("football_data_org_schedule_standings")

    return BootstrapSummary(tuple(run_ids), tuple(unavailable))
