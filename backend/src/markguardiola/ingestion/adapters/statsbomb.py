from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import timedelta

from markguardiola.ingestion.adapters.http import CachePolicy, HttpAdapterClient
from markguardiola.ingestion.contracts import IngestionScope, RawPayload


class StatsBombOpenDataAdapter:
    key = "statsbomb_open_data"
    name = "StatsBomb Open Data"
    adapter_version = "1.0.0"
    base_url = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"

    def __init__(self, client: HttpAdapterClient) -> None:
        self._client = client

    async def iter_raw(self, scope: IngestionScope) -> AsyncIterator[RawPayload]:
        competitions = await self._client.get(
            f"{self.base_url}/competitions.json",
            cache_policy=CachePolicy(timedelta(days=1)),
            provider_object_id="competitions",
            schema_hint="statsbomb-open-data:competitions",
        )
        yield competitions
        catalog = json.loads(competitions.content)
        matching = [
            item
            for item in catalog
            if item.get("competition_name") == scope.competition
            and (
                not scope.seasons or str(item.get("season_name")).replace("/", "-") in scope.seasons
            )
        ]

        for item in matching:
            competition_id = int(item["competition_id"])
            season_id = int(item["season_id"])
            yield await self._client.get(
                f"{self.base_url}/matches/{competition_id}/{season_id}.json",
                cache_policy=CachePolicy(timedelta(days=3650), immutable=True),
                provider_object_id=f"matches:{competition_id}:{season_id}",
                schema_hint="statsbomb-open-data:matches",
            )
