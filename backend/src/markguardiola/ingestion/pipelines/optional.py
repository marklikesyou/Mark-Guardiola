from markguardiola.core.config import Settings
from markguardiola.db.session import get_session_factory
from markguardiola.ingestion.adapters.soccerdata_optional import (
    PROVIDERS,
    SoccerdataOptionalAdapter,
)
from markguardiola.ingestion.contracts import IngestionScope
from markguardiola.ingestion.pipelines.coordinator import IngestionCoordinator


async def ingest_optional(
    settings: Settings,
    season: str,
    providers: tuple[str, ...],
    *,
    allow_browser: bool = False,
) -> list[dict[str, object]]:
    if set(providers).difference(PROVIDERS):
        raise ValueError()
    results: list[dict[str, object]] = []
    async with get_session_factory()() as session:
        for provider in providers:
            adapter = SoccerdataOptionalAdapter(
                provider,
                cache_dir=settings.data_root / "raw" / ".soccerdata" / provider,
                allow_browser=allow_browser,
            )
            try:
                run = await IngestionCoordinator(session, settings.data_root).ingest(
                    adapter,
                    IngestionScope(seasons=(season,)),
                )
                results.append(
                    {
                        "source": provider,
                        "status": "bronze_only",
                        "run_id": str(run.id),
                        "payloads": run.records_seen,
                        "canonical_feature_coverage_verified": False,
                    }
                )
            except Exception:
                results.append(
                    {
                        "source": provider,
                        "status": "unavailable",
                        "error": "unavailable",
                    }
                )
    return results
