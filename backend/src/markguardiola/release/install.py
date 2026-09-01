from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Literal

from psycopg import sql
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from markguardiola.core.config import Settings, get_settings
from markguardiola.db.base import Base
from markguardiola.db.session import get_engine, get_session_factory
from markguardiola.entity_resolution.periods import materialize_membership_periods
from markguardiola.entity_resolution.reconcile import reconcile_identities
from markguardiola.features.pipeline import FEATURE_SCHEMA_VERSION
from markguardiola.ingestion.pipelines.bootstrap import bootstrap, current_season_label
from markguardiola.ml.pipeline import predict_upcoming, rebuild_models
from markguardiola.ml.registry import LocalModelRegistry
from markguardiola.ml.targets import TARGETS
from markguardiola.release.bundle import LATEST_PREDICTION, connect, restore_bundle
from markguardiola.release.manifest import FOOTBALL_TABLES, REQUIRED_TABLES
from markguardiola.release.tutorial import provision_tutorial_league
from markguardiola.release.tutorial_photos import enrich_tutorial_photos


class InstallOptions(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MARK_", extra="ignore")
    bootstrap_mode: Literal["auto", "bundle", "rebuild"] = "auto"
    bundle_file: str = ""
    bundle_sha256: str = ""

    @model_validator(mode="after")
    def validate_bundle_selection(self) -> InstallOptions:
        if bool(self.bundle_file) != bool(self.bundle_sha256):
            raise ValueError()
        if self.bootstrap_mode == "bundle" and not self.bundle_file:
            raise ValueError()
        if self.bootstrap_mode == "rebuild" and self.bundle_file:
            raise ValueError()
        return self


def installation_state(settings: Settings) -> tuple[bool, bool]:

    populated, private = False, False
    with connect(settings) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        for table in Base.metadata.sorted_tables:
            row = connection.execute(
                sql.SQL("SELECT EXISTS (SELECT 1 FROM {})").format(sql.Identifier(table.name))
            ).fetchone()
            if row and row[0]:
                populated = True
                private |= table.name not in FOOTBALL_TABLES
    return populated, private


def assert_installation_ready(settings: Settings) -> dict[str, Any]:

    with connect(settings) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        for table in REQUIRED_TABLES:
            row = connection.execute(
                sql.SQL("SELECT EXISTS (SELECT 1 FROM {})").format(sql.Identifier(table))
            ).fetchone()
            if not row or not row[0]:
                raise ValueError()
        versions = dict(
            connection.execute(
                "SELECT target, version FROM model_versions WHERE status = 'champion' "
                "AND feature_schema_version = %s",
                (FEATURE_SCHEMA_VERSION,),
            ).fetchall()
        )
        missing = (set(TARGETS) - {"base_rating"}) - set(versions)
        if missing:
            raise ValueError()
        registry = LocalModelRegistry(settings.artifact_root / "models")
        for target, version in versions.items():
            champion, manifest = registry.load_champion(target)
            if manifest.get("version") != version or not hasattr(champion, "feature_names"):
                raise ValueError()
        run = connection.execute(
            "SELECT id, model_versions, prediction_cutoff FROM prediction_runs "
            f"WHERE id = ({LATEST_PREDICTION})"
        ).fetchone()
        if not run or run[1] != versions:
            raise ValueError()
        coverage = connection.execute(
            "SELECT count(DISTINCT p.player_id), count(DISTINCT p.match_id) "
            "FROM player_match_predictions p JOIN matches m ON m.id = p.match_id "
            "WHERE p.prediction_run_id = %s AND m.kickoff_at > now() "
            "AND m.status NOT IN ('finished', 'cancelled', 'abandoned')",
            (run[0],),
        ).fetchone()
        if not coverage or not coverage[0] or not coverage[1]:
            raise ValueError()
        tutorial = connection.execute(
            "SELECT l.id, "
            "count(DISTINCT ft.id) FILTER (WHERE ft.is_user_team), "
            "count(DISTINCT ft.id) FILTER (WHERE NOT ft.is_user_team), "
            "count(DISTINCT re.id) FILTER (WHERE re.active), "
            "count(DISTINCT me.id) FILTER (WHERE me.available) "
            "FROM leagues l "
            "LEFT JOIN fantasy_teams ft ON ft.league_id = l.id "
            "LEFT JOIN roster_entries re ON re.fantasy_team_id = ft.id "
            "LEFT JOIN market_entries me ON me.league_id = l.id "
            "WHERE l.name = 'Tutorial' GROUP BY l.id"
        ).fetchone()
        if (
            not tutorial
            or tutorial[1] != 1
            or tutorial[2] < 1
            or tutorial[3] < 50
            or not tutorial[4]
        ):
            raise ValueError()
    return {
        "status": "ready",
        "champions": len(versions),
        "players_with_forecasts": coverage[0],
        "fixtures_with_forecasts": coverage[1],
        "prediction_cutoff": run[2].isoformat(),
    }


async def _canonicalize() -> None:
    async with get_session_factory()() as session, session.begin():
        await reconcile_identities(session, apply=True)
        await materialize_membership_periods(session)


async def _prepare(settings: Settings, *, restored: bool) -> dict[str, Any]:
    warnings: list[str] = []
    try:
        summary = await bootstrap(
            settings,
            first_start_year=int(current_season_label()[:4]) if restored else 2013,
        )
        warnings.extend(summary.unavailable_enrichments)
    except Exception:
        if not restored:
            raise
        warnings.append("current_season_refresh")
    await _canonicalize()
    if restored:
        result = await predict_upcoming()
    else:
        result = await rebuild_models({"include_external": True, "random_seed": 2026})
    async with get_session_factory()() as session:
        tutorial = await provision_tutorial_league(session)
        await session.commit()
    try:
        tutorial_photos = await enrich_tutorial_photos(settings)
    except Exception:
        tutorial_photos = {"status": "unavailable"}
        warnings.append("tutorial_player_photos")
    return {
        "processing": result,
        "tutorial": tutorial,
        "tutorial_photos": tutorial_photos,
        "unavailable_enrichments": warnings,
    }


def install_data(settings: Settings, options: InstallOptions) -> dict[str, Any]:
    populated, private = installation_state(settings)
    if populated and options.bundle_file:
        return {**assert_installation_ready(settings), "bootstrap": "existing-installation"}
    if populated and options.bootstrap_mode == "auto":
        try:
            return {**assert_installation_ready(settings), "bootstrap": "existing-installation"}
        except (ValueError, FileNotFoundError):
            if private:
                raise ValueError() from None
    if private:
        raise ValueError()
    restored = bool(options.bundle_file)
    if restored:
        restore_bundle(settings, Path(options.bundle_file), expected_sha256=options.bundle_sha256)

    async def prepare_and_close() -> dict[str, Any]:
        try:
            return await _prepare(settings, restored=restored)
        finally:
            await get_engine().dispose()
            get_session_factory.cache_clear()
            get_engine.cache_clear()

    result = asyncio.run(prepare_and_close())
    return {
        **assert_installation_ready(settings),
        **result,
        "bootstrap": "trusted-bundle" if restored else "real-source-rebuild",
    }


def main() -> None:
    print(json.dumps(install_data(get_settings(), InstallOptions()), indent=2), flush=True)
