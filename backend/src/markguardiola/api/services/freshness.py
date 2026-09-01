from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from markguardiola.api.contracts import SourceStatusView
from markguardiola.core.config import Settings
from markguardiola.db.models import DataSource, IngestionRun, RawObject

_SOURCES = {
    "pannadata": (
        "Pannadata",
        ("historical_player_statistics", "lineups", "events", "shots"),
        7 * 24,
    ),
    "football_data_co_uk": (
        "Football-Data.co.uk",
        ("results", "team_statistics", "historical_odds"),
        48,
    ),
    "understat": ("Understat", ("schedule", "team_xg"), 24),
    "api_football": (
        "API-Football",
        ("schedule", "current_lineups", "injuries", "statistics", "standings", "transfers", "odds"),
        6,
    ),
    "football_data_org": ("football-data.org", ("schedule", "standings"), 24),
    "clubelo": ("ClubElo", ("bronze_rating_snapshots",), 7 * 24),
    "fbref": ("FBref", ("bronze_player_statistics", "bronze_lineups"), 7 * 24),
    "sofascore": ("Sofascore", ("bronze_schedule",), 48),
    "whoscored": ("WhoScored", ("bronze_events", "bronze_absences"), 48),
}


async def source_statuses(session: AsyncSession, settings: Settings) -> list[SourceStatusView]:
    sources = {source.key: source for source in (await session.scalars(select(DataSource))).all()}
    observations = {
        source_id: observed
        for source_id, observed in (
            await session.execute(
                select(RawObject.source_id, func.max(RawObject.ingested_at)).group_by(
                    RawObject.source_id
                )
            )
        ).all()
    }
    successes = {
        source_id: completed
        for source_id, completed in (
            await session.execute(
                select(IngestionRun.source_id, func.max(IngestionRun.completed_at))
                .where(IngestionRun.status == "succeeded")
                .group_by(IngestionRun.source_id)
            )
        ).all()
    }
    ranked = select(
        IngestionRun.source_id,
        IngestionRun.status,
        func.row_number()
        .over(partition_by=IngestionRun.source_id, order_by=IngestionRun.started_at.desc())
        .label("rank"),
    ).subquery()
    latest_statuses = {
        source_id: state
        for source_id, state in (
            await session.execute(
                select(ranked.c.source_id, ranked.c.status).where(ranked.c.rank == 1)
            )
        ).all()
    }
    now = datetime.now(UTC)
    result: list[SourceStatusView] = []
    for key, (name, capabilities, hours) in _SOURCES.items():
        source = sources.get(key)
        latest = latest_statuses.get(source.id) if source else None
        success = successes.get(source.id) if source else None
        observed = observations.get(source.id) if source else None
        state = _source_state(
            configured=not (
                (key == "api_football" and settings.api_football_key is None)
                or (key == "football_data_org" and settings.football_data_org_key is None)
            ),
            enabled=source is None or source.enabled,
            latest_observation=observed,
            latest_success=success,
            stale_after=timedelta(hours=hours),
            now=now,
        )
        result.append(
            SourceStatusView.model_validate(
                {
                    "key": key,
                    "name": name,
                    "status": state,
                    "capabilities": capabilities,
                    "latest_observation": observed,
                    "latest_successful_ingestion": success,
                    "latest_attempt_status": latest,
                }
            )
        )
    return result


def _source_state(
    *,
    configured: bool,
    enabled: bool,
    latest_observation: datetime | None,
    latest_success: datetime | None,
    stale_after: timedelta,
    now: datetime,
) -> str:

    if not configured:
        return "unconfigured"
    if not enabled or latest_observation is None or latest_success is None:
        return "unavailable"
    if now - latest_observation > stale_after:
        return "stale"
    return "available"
