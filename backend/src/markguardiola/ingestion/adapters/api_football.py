from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncIterator, Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from pydantic import SecretStr

from markguardiola.ingestion.adapters.http import CachePolicy, HttpAdapterClient, json_payload
from markguardiola.ingestion.adapters.quota import QuotaExceededError as QuotaExceededError
from markguardiola.ingestion.adapters.quota import RequestQuota
from markguardiola.ingestion.contracts import IngestionScope, RawPayload


class ApiFootballAdapter:
    key = "api_football"
    name = "API-Football"
    adapter_version = "1.2.0"
    base_url = "https://v3.football.api-sports.io"

    def __init__(
        self,
        client: HttpAdapterClient,
        api_key: SecretStr,
        *,
        daily_limit: int = 100,
        league_id: int = 135,
        quota_ledger: Path | None = None,
    ) -> None:
        self._client = client
        self._api_key = api_key
        self._quota = RequestQuota(
            daily_limit,
            ledger_path=quota_ledger,
            account=hashlib.sha256(api_key.get_secret_value().encode()).hexdigest(),
        )
        self._league_id = league_id

    async def iter_raw(self, scope: IngestionScope) -> AsyncIterator[RawPayload]:
        if not scope.seasons:
            raise ValueError()
        data_types = scope.data_types or (
            "fixtures",
            "fixture_details",
            "teams",
            "players",
            "injuries",
            "standings",
        )
        details = {"fixture_details", "events", "lineups", "players_statistics", "team_statistics"}
        want_details = bool(details.intersection(data_types))
        regular = tuple(item for item in data_types if item not in details | {"transfers"})
        if (
            (want_details and not scope.fixture_ids)
            or ("transfers" in data_types and not scope.team_ids)
        ) and "fixtures" not in regular:
            regular = ("fixtures", *regular)
        for season_label in scope.seasons:
            season_start = int(season_label[:4])
            observed_fixtures: dict[str, tuple[datetime, bool]] = {}
            team_ids = set(scope.team_ids)

            requests = list(self._requests(regular, season_start))
            if want_details and scope.fixture_ids:
                for fixture_id in reversed(dict.fromkeys(scope.fixture_ids)):
                    requests.insert(
                        0, ("fixtures", {"id": int(fixture_id)}, CachePolicy(timedelta(minutes=30)))
                    )
            for endpoint, params, policy in requests:
                async for payload in self._pages(endpoint, params, policy, season_start):
                    yield payload
                    if endpoint == "fixtures" and "id" not in params:
                        for row in json_payload(payload)["response"]:
                            fixture = row["fixture"]
                            observed_fixtures[str(fixture["id"])] = (
                                datetime.fromisoformat(fixture["date"]),
                                fixture["status"]["short"] in {"FT", "AET", "PEN"},
                            )
                            team_ids.update(str(team["id"]) for team in row["teams"].values())
                if (
                    endpoint == "fixtures"
                    and "id" not in params
                    and want_details
                    and not scope.fixture_ids
                ):
                    now = datetime.now(UTC)
                    lower = scope.since or now - timedelta(days=7)
                    upper = scope.until or now + timedelta(days=2)
                    for fixture_id, (kickoff, finished) in sorted(
                        observed_fixtures.items(), key=lambda item: item[1][0], reverse=True
                    ):
                        if lower <= kickoff <= upper:
                            async for detail in self._pages(
                                "fixtures",
                                {"id": int(fixture_id)},
                                CachePolicy(
                                    timedelta(hours=24) if finished else timedelta(minutes=30)
                                ),
                                season_start,
                            ):
                                yield detail
            if "transfers" in data_types:
                if not team_ids:
                    raise ValueError()
                for team_id in sorted(team_ids):
                    async for payload in self._pages(
                        "transfers",
                        {"team": int(team_id)},
                        CachePolicy(timedelta(days=1)),
                        season_start,
                    ):
                        yield payload

    async def _pages(
        self,
        endpoint: str,
        params: dict[str, str | int | float | bool],
        policy: CachePolicy,
        season_start: int,
        *,
        maximum_pages: int | None = None,
    ) -> AsyncIterator[RawPayload]:
        while True:
            identity = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:16]
            payload = await self._client.get(
                f"{self.base_url}/{endpoint}",
                params=params,
                headers={"x-apisports-key": self._api_key.get_secret_value()},
                cache_policy=policy,
                provider_object_id=(f"{endpoint}:{season_start}:{identity}"),
                schema_hint=f"api-football-v3:{endpoint}",
                before_request=self._quota.reserve,
                after_response=self._observe_response,
                cache_response=_cacheable_response,
            )

            yield payload
            body = json_payload(payload)
            if body.get("errors"):
                raise RuntimeError()
            paging = body.get("paging", {})
            page, total = int(paging.get("current", 1)), int(paging.get("total", 1))
            if page != params.get("page", 1) or not 0 <= total <= 10000:
                raise ValueError()
            if page >= total or (maximum_pages is not None and page >= maximum_pages):
                break
            params = {**params, "page": page + 1}

    async def search_players(self, *, season: int, search: str) -> AsyncIterator[RawPayload]:

        async for payload in self._pages(
            "players",
            {"league": self._league_id, "season": season, "search": search},
            CachePolicy(timedelta(days=7)),
            season,
            maximum_pages=1,
        ):
            yield payload

    async def _observe_response(self, response: httpx.Response) -> None:
        remaining = response.headers.get("x-ratelimit-requests-remaining")
        if remaining is not None:
            await self._quota.observe_remaining(int(remaining))

    def _requests(
        self, data_types: Iterable[str], season: int
    ) -> Iterable[tuple[str, dict[str, str | int | float | bool], CachePolicy]]:
        for data_type in data_types:
            if data_type == "fixtures":
                yield (
                    "fixtures",
                    {"league": self._league_id, "season": season},
                    CachePolicy(timedelta(hours=2)),
                )
            elif data_type == "teams":
                yield (
                    "teams",
                    {"league": self._league_id, "season": season},
                    CachePolicy(timedelta(days=7)),
                )
            elif data_type == "players":
                yield (
                    "players",
                    {"league": self._league_id, "season": season, "page": 1},
                    CachePolicy(timedelta(hours=12)),
                )
            elif data_type == "injuries":
                yield (
                    "injuries",
                    {"league": self._league_id, "season": season},
                    CachePolicy(timedelta(minutes=30)),
                )
            elif data_type in {"standings", "odds"}:
                yield (
                    data_type,
                    {"league": self._league_id, "season": season},
                    CachePolicy(
                        timedelta(hours=6) if data_type == "standings" else timedelta(hours=1)
                    ),
                )
            else:
                raise ValueError()


def _cacheable_response(response: httpx.Response) -> bool:
    try:
        body = response.json()
    except ValueError:
        return False
    return isinstance(body, dict) and not body.get("errors") and "response" in body
