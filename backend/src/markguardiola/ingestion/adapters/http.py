from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from markguardiola.ingestion.contracts import RawPayload


@dataclass(frozen=True, slots=True)
class CachePolicy:
    ttl: timedelta
    immutable: bool = False


class FileResponseCache:
    def __init__(self, root: Path) -> None:
        self._root = root

    def get(self, key: str, policy: CachePolicy, now: datetime) -> RawPayload | None:
        path = self._path(key)
        metadata_path = path.with_suffix(".metadata.json")
        if not path.exists() or not metadata_path.exists():
            return None
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        retrieved_at = datetime.fromisoformat(metadata["retrieved_at"])
        if not policy.immutable and now - retrieved_at > policy.ttl:
            return None
        return RawPayload(
            provider_object_id=metadata.get("provider_object_id"),
            request_url=metadata["request_url"],
            request_params=metadata["request_params"],
            media_type=metadata["media_type"],
            content=path.read_bytes(),
            event_time=(
                datetime.fromisoformat(metadata["event_time"])
                if metadata.get("event_time")
                else None
            ),
            available_at=datetime.fromisoformat(metadata["available_at"]),
            retrieved_at=retrieved_at,
            response_headers=metadata.get("response_headers", {}),
            schema_hint=metadata.get("schema_hint"),
        )

    def put(self, key: str, payload: RawPayload) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        path = self._path(key)
        path.write_bytes(payload.content)
        metadata = {
            "provider_object_id": payload.provider_object_id,
            "request_url": payload.request_url,
            "request_params": payload.request_params,
            "media_type": payload.media_type,
            "event_time": payload.event_time.isoformat() if payload.event_time else None,
            "available_at": payload.available_at.isoformat(),
            "retrieved_at": payload.retrieved_at.isoformat(),
            "response_headers": payload.response_headers,
            "schema_hint": payload.schema_hint,
        }
        path.with_suffix(".metadata.json").write_text(
            json.dumps(metadata, sort_keys=True), encoding="utf-8"
        )

    def _path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self._root / f"{digest}.payload"


class HttpAdapterClient:
    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        cache: FileResponseCache | None = None,
        retries: int = 3,
    ) -> None:
        self._client = client
        self._cache = cache
        self._retries = retries

    async def get(
        self,
        url: str,
        *,
        params: dict[str, str | int | float | bool] | None = None,
        headers: dict[str, str] | None = None,
        cache_policy: CachePolicy | None = None,
        provider_object_id: str | None = None,
        schema_hint: str | None = None,
        before_request: Callable[[], Awaitable[None]] | None = None,
        after_response: Callable[[httpx.Response], Awaitable[None]] | None = None,
        cache_response: Callable[[httpx.Response], bool] | None = None,
    ) -> RawPayload:
        safe_params = params or {}
        key_parts: list[object] = [url, sorted(safe_params.items())]
        credentials = sorted(
            (key.lower(), value)
            for key, value in (headers or {}).items()
            if key.lower() in {"authorization", "x-apisports-key", "x-auth-token"}
        )
        if credentials:
            key_parts.append(hashlib.sha256(json.dumps(credentials).encode()).hexdigest())
        cache_key = json.dumps(key_parts, separators=(",", ":"))
        now = datetime.now(UTC)
        if self._cache is not None and cache_policy is not None:
            cached = self._cache.get(cache_key, cache_policy, now)
            if cached is not None:
                return cached

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=60, follow_redirects=True)
        try:
            response: httpx.Response | None = None
            for attempt in range(self._retries):
                if before_request is not None:
                    await before_request()
                response = await client.get(url, params=safe_params, headers=headers)
                if after_response is not None:
                    await after_response(response)
                if response.status_code not in {429, 500, 502, 503, 504}:
                    break
                if attempt + 1 < self._retries:
                    retry_after = min(float(response.headers.get("retry-after", "1")), 10.0)
                    await asyncio.sleep(retry_after * (2**attempt))
            assert response is not None
            response.raise_for_status()
            retrieved_at = datetime.now(UTC)
            available_at = _header_datetime(response.headers.get("last-modified")) or retrieved_at
            payload = RawPayload(
                provider_object_id=provider_object_id,
                request_url=str(response.request.url.copy_with(query=None)),
                request_params=safe_params,
                media_type=response.headers.get("content-type", "application/octet-stream").split(
                    ";", maxsplit=1
                )[0],
                content=response.content,
                available_at=available_at,
                retrieved_at=retrieved_at,
                response_headers={key.lower(): value for key, value in response.headers.items()},
                schema_hint=schema_hint,
            )
            if (
                self._cache is not None
                and cache_policy is not None
                and (cache_response is None or cache_response(response))
            ):
                self._cache.put(cache_key, payload)
            return payload
        finally:
            if owns_client:
                await client.aclose()


def json_payload(payload: RawPayload) -> dict[str, Any]:
    parsed = json.loads(payload.content)
    if not isinstance(parsed, dict):
        raise ValueError()
    return parsed


def _header_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=UTC)
    except ValueError:
        return None
