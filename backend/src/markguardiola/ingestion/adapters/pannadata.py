from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any

from markguardiola.ingestion.adapters.http import CachePolicy, HttpAdapterClient
from markguardiola.ingestion.contracts import IngestionScope, RawPayload


class PannadataAdapter:
    key = "pannadata"
    name = "Pannadata"
    adapter_version = "1.0.0"
    base_url = "https://github.com/peteowen1/pannadata"
    releases_api = "https://api.github.com/repos/peteowen1/pannadata/releases/tags/opta-latest"

    def __init__(self, client: HttpAdapterClient) -> None:
        self._client = client

    async def iter_raw(self, scope: IngestionScope) -> AsyncIterator[RawPayload]:
        manifest = await self._client.get(
            self.releases_api,
            headers={"Accept": "application/vnd.github+json"},
            cache_policy=CachePolicy(timedelta(hours=6)),
            provider_object_id="opta-latest-release",
            schema_hint="github-release-v3",
        )
        yield manifest
        release = json.loads(manifest.content)
        if not isinstance(release, dict):
            raise ValueError()
        assets = release.get("assets", [])
        if not isinstance(assets, list):
            raise ValueError()
        selected = sorted(
            select_assets(assets, scope.data_types, competition=scope.competition),
            key=lambda asset: _asset_priority(str(asset["name"])),
        )
        if not selected:
            raise ValueError()
        for asset in selected:
            url = str(asset["browser_download_url"])
            name = str(asset["name"])
            yield await self._client.get(
                url,
                cache_policy=CachePolicy(timedelta(days=1)),
                provider_object_id=str(asset.get("id", name)),
                schema_hint=f"pannadata-opta:{name}",
            )


def select_assets(
    assets: list[Any],
    requested_data_types: tuple[str, ...],
    *,
    competition: str = "Serie A",
) -> list[dict[str, Any]]:
    wanted = requested_data_types or ("fixtures", "player_stats", "lineups", "shots", "events")
    competition_slug = competition.replace(" ", "_").casefold()
    names = {
        "fixtures": {"opta_fixtures.parquet"},
        "player_stats": {"opta_player_stats.parquet"},
        "lineups": {"opta_lineups.parquet"},
        "shots": {"opta_shots.parquet", "opta_shot_events.parquet"},
        "events": {f"events_{competition_slug}.parquet"},
        "xmetrics": {"opta_xmetrics.parquet", "opta_xmetrics_bymatch.parquet"},
        "manifest": {"opta-manifest.parquet", "bus_manifest.json"},
    }
    selected: list[dict[str, Any]] = []
    for untyped_asset in assets:
        if not isinstance(untyped_asset, dict) or "name" not in untyped_asset:
            continue
        asset = untyped_asset
        name = str(asset["name"]).lower()
        if not name.endswith((".parquet", ".json", ".zip", ".tar.gz")):
            continue
        if any(name in names.get(kind, set()) for kind in wanted):
            selected.append(asset)
    return selected


def _asset_priority(name: str) -> tuple[int, str]:
    lowered = name.lower()
    priorities = (
        ("manifest", 0),
        ("fixture", 1),
        ("player", 2),
        ("lineup", 3),
        ("shot", 4),
        ("event", 5),
    )
    return next(
        ((priority, lowered) for token, priority in priorities if token in lowered),
        (99, lowered),
    )
