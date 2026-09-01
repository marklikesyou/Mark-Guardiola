from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta

from pydantic import SecretStr

from markguardiola.ingestion.adapters.http import CachePolicy, HttpAdapterClient
from markguardiola.ingestion.contracts import IngestionScope, RawPayload


class FootballDataOrgAdapter:
    key = "football_data_org"
    name = "football-data.org"
    adapter_version = "1.0.0"
    base_url = "https://api.football-data.org/v4"

    def __init__(self, client: HttpAdapterClient, api_key: SecretStr) -> None:
        self._client = client
        self._api_key = api_key

    async def iter_raw(self, scope: IngestionScope) -> AsyncIterator[RawPayload]:
        headers = {"X-Auth-Token": self._api_key.get_secret_value()}
        data_types = scope.data_types or ("matches", "standings", "teams")
        params: dict[str, str | int | float | bool] = {}
        if scope.seasons:
            params["season"] = int(scope.seasons[-1][:4])
        for resource in data_types:
            if resource not in {"matches", "standings", "teams", "scorers"}:
                raise ValueError()
            yield await self._client.get(
                f"{self.base_url}/competitions/{scope.competition_code}/{resource}",
                params=params,
                headers=headers,
                cache_policy=CachePolicy(
                    timedelta(minutes=30) if resource == "matches" else timedelta(hours=6)
                ),
                provider_object_id=f"{scope.competition_code}:{resource}",
                schema_hint=f"football-data-org-v4:{resource}",
            )
