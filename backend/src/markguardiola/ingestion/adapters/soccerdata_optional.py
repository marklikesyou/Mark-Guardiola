from __future__ import annotations

import asyncio
import hashlib
import importlib
import io
import multiprocessing
import os
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from markguardiola.ingestion.contracts import IngestionScope, RawPayload

PROVIDERS = {
    "clubelo": ("ClubElo", "http://api.clubelo.com", {"ratings", "team_history"}),
    "fbref": ("FBref", "https://fbref.com", {"schedule", "player_match_stats", "lineups"}),
    "sofascore": ("Sofascore", "https://www.sofascore.com", {"schedule", "standings"}),
    "whoscored": ("WhoScored", "https://www.whoscored.com", {"schedule", "events", "absences"}),
}


class SoccerdataOptionalAdapter:
    adapter_version = "1.0.0"

    def __init__(
        self,
        provider: str,
        *,
        cache_dir: Path,
        allow_browser: bool = False,
        timeout_seconds: float = 120,
        reader_factory: Callable[..., Any] | None = None,
    ) -> None:
        if provider not in PROVIDERS:
            raise ValueError()
        self.key = provider
        self.name = f"{PROVIDERS[provider][0]} via soccerdata (optional)"
        self.base_url = PROVIDERS[provider][1]
        self._cache_dir = cache_dir.resolve()
        self._allow_browser = allow_browser
        self._timeout = timeout_seconds
        self._reader_factory = reader_factory

    async def iter_raw(self, scope: IngestionScope) -> AsyncIterator[RawPayload]:
        if len(scope.seasons) != 1:
            raise ValueError()
        types = scope.data_types or (("ratings",) if self.key == "clubelo" else ("schedule",))
        if set(types).difference(PROVIDERS[self.key][2]):
            raise ValueError()
        if self.key in {"fbref", "whoscored"} and not self._allow_browser:
            raise RuntimeError()
        if set(types).intersection({"lineups", "events", "absences"}) and not scope.fixture_ids:
            raise ValueError()
        if "team_history" in types and not scope.team_ids:
            raise ValueError()
        if self._reader_factory is not None:
            payloads, error = await asyncio.to_thread(
                _collect,
                self.key,
                self._cache_dir,
                scope,
                types,
                self._reader_factory,
            )
        else:
            payloads, error = await self._isolated_collect(scope, types)
        for payload in payloads:
            yield payload
        if error:
            raise RuntimeError()

    async def _isolated_collect(
        self,
        scope: IngestionScope,
        types: tuple[str, ...],
    ) -> tuple[list[RawPayload], str | None]:
        context = multiprocessing.get_context("spawn")
        receiver, sender = context.Pipe(duplex=False)
        process = context.Process(
            target=_worker,
            args=(
                sender,
                self.key,
                self._cache_dir,
                scope,
                types,
            ),
            daemon=True,
        )
        process.start()
        sender.close()
        try:
            async with asyncio.timeout(self._timeout):
                while not receiver.poll():
                    if not process.is_alive():
                        raise RuntimeError()
                    await asyncio.sleep(0.1)
                result: tuple[list[RawPayload], str | None] = await asyncio.to_thread(receiver.recv)
                return result
        finally:
            receiver.close()
            if process.is_alive():
                process.terminate()
            await asyncio.to_thread(process.join, 5)
            if process.is_alive():
                process.kill()
                await asyncio.to_thread(process.join, 5)
            process.close()


def _worker(
    channel: Any, provider: str, cache: Path, scope: IngestionScope, types: tuple[str, ...]
) -> None:
    try:
        channel.send(_collect(provider, cache, scope, types))
    finally:
        channel.close()


def _collect(
    provider: str,
    cache: Path,
    scope: IngestionScope,
    types: tuple[str, ...],
    factory: Callable[..., Any] | None = None,
) -> tuple[list[RawPayload], str | None]:
    payloads: list[RawPayload] = []
    reader = None
    try:
        os.environ.setdefault("SOCCERDATA_DIR", str(cache.parent))
        kwargs: dict[str, Any] = {"data_dir": cache}
        if provider != "clubelo":
            kwargs.update(leagues="ITA-Serie A", seasons=scope.seasons[0])
        if provider in {"fbref", "whoscored"}:
            kwargs.update(headless=True)
        reader = (
            factory or getattr(importlib.import_module("soccerdata"), PROVIDERS[provider][0])
        )(**kwargs)
        original_get = reader.get

        def capture(url: str, *args: Any, **options: Any) -> io.BytesIO:
            response = original_get(url, *args, **options)
            content = response.read()
            if isinstance(content, str):
                content = content.encode()
            now = datetime.now(UTC)
            payloads.append(
                RawPayload(
                    provider_object_id=hashlib.sha256(url.encode()).hexdigest(),
                    request_url=url,
                    content=content,
                    media_type="application/octet-stream",
                    available_at=now,
                    retrieved_at=now,
                    schema_hint=f"soccerdata-{provider}:original-response",
                )
            )
            return io.BytesIO(content)

        reader.get = capture
        for kind in types:
            for frame in _frames(reader, kind, scope):
                if frame.empty:
                    raise ValueError()
                buffer = io.BytesIO()
                frame.to_parquet(buffer, index=True)
                now = datetime.now(UTC)
                payloads.append(
                    RawPayload(
                        provider_object_id=f"{provider}:{scope.seasons[0]}:{kind}:{len(payloads)}",
                        request_url=PROVIDERS[provider][1],
                        request_params={"season": scope.seasons[0]},
                        media_type="application/vnd.apache.parquet",
                        content=buffer.getvalue(),
                        available_at=now,
                        retrieved_at=now,
                        schema_hint=f"soccerdata-{provider}:{kind}",
                    )
                )
        return payloads, None
    except Exception:
        return payloads, "unavailable"
    finally:
        driver = getattr(reader, "_driver", None)
        if driver is not None:
            driver.quit()


def _frames(reader: Any, kind: str, scope: IngestionScope) -> list[Any]:
    if kind == "ratings":
        return [
            reader.read_by_date(
                (scope.since or datetime(int(scope.seasons[0][:4]), 7, 1)).date().isoformat()
            )
        ]
    if kind == "team_history":
        return [reader.read_team_history(team) for team in scope.team_ids]
    if kind == "schedule":
        return [reader.read_schedule()]
    if kind == "standings":
        return [reader.read_league_table()]
    if kind == "player_match_stats":
        return [reader.read_player_match_stats()]
    if kind == "lineups":
        return [reader.read_lineup(match_id=fixture) for fixture in scope.fixture_ids]
    ids = [int(fixture) for fixture in scope.fixture_ids]
    if kind == "events":
        return [reader.read_events(match_id=ids, output_fmt="events", on_error="raise")]
    if kind == "absences":
        return [reader.read_missing_players(match_id=ids)]
    raise ValueError()
