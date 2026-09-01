from __future__ import annotations

import asyncio
import importlib
import io
import os
import re
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from markguardiola.ingestion.contracts import IngestionScope, RawPayload


class UnderstatAdapter:
    key = "understat"
    name = "Understat via soccerdata"
    adapter_version = "1.1.0"
    base_url = "https://understat.com"

    def __init__(
        self, reader_factory: Callable[..., Any] | None = None, *, cache_dir: Path | None = None
    ) -> None:
        self._reader_factory = reader_factory or _soccerdata_reader
        if cache_dir is None:
            from markguardiola.core.config import get_settings

            cache_dir = get_settings().data_root / "raw" / ".soccerdata" / "Understat"
        self._cache_dir = cache_dir.resolve()

    async def iter_raw(self, scope: IngestionScope) -> AsyncIterator[RawPayload]:
        if not scope.seasons:
            raise ValueError()
        for season in scope.seasons:
            season_start = int(season[:4])
            reader = self._reader_factory(
                leagues="ITA-Serie A", seasons=season, data_dir=self._cache_dir
            )
            for index, data_type in enumerate(scope.data_types or ("team_match_stats",)):
                failure_type: type[Exception] | None = None
                try:
                    frame = await asyncio.to_thread(_read_frame, reader, data_type, index > 0)
                except Exception as exc:
                    failure_type = type(exc)

                for path in sorted(self._cache_dir.glob("*.json")):
                    url = _cache_url(path.name, season_start)
                    if url is None:
                        continue
                    retrieved = datetime.fromtimestamp(path.stat().st_mtime, UTC)
                    yield RawPayload(
                        provider_object_id=f"understat:raw:{path.name}",
                        request_url=url,
                        media_type="application/json",
                        content=path.read_bytes(),
                        available_at=retrieved,
                        retrieved_at=retrieved,
                        schema_hint="understat:original-response",
                    )
                if failure_type is not None:
                    raise failure_type() from None
                buffer = io.BytesIO()
                frame.to_parquet(buffer, index=True)
                now = datetime.now(UTC)
                yield RawPayload(
                    provider_object_id=f"understat:ITA-Serie A:{season}:{data_type}",
                    request_url=f"{self.base_url}/league/Serie_A/{season_start}",
                    media_type="application/vnd.apache.parquet",
                    content=buffer.getvalue(),
                    available_at=now,
                    retrieved_at=now,
                    schema_hint=f"soccerdata-understat:{data_type}",
                    request_params={"season_start": season_start},
                )


def _soccerdata_reader(**kwargs: Any) -> Any:

    os.environ.setdefault("SOCCERDATA_DIR", str(Path(kwargs["data_dir"]).parent))
    try:
        sd = importlib.import_module("soccerdata")
    except ImportError:
        raise RuntimeError() from None
    return sd.Understat(**kwargs)


def _cache_url(filename: str, season_start: int) -> str | None:
    if filename == "leagues.json":
        return "https://understat.com/getStatData"
    if re.fullmatch(rf"league_\d+_season_{season_start}\.json", filename):
        return f"https://understat.com/getLeagueData/Serie_A/{season_start}"
    match = re.fullmatch(r"match_(\d+)\.json", filename)
    if match:
        return f"https://understat.com/getMatchData/{match[1]}"
    return None


def _read_frame(reader: Any, data_type: str, force_cache: bool = False) -> Any:
    if data_type == "schedule":
        return reader.read_schedule(force_cache=force_cache)
    if data_type == "player_match_stats":
        return reader.read_player_match_stats()
    if data_type == "shot_events":
        return reader.read_shot_events()
    if data_type == "team_match_stats":
        return reader.read_team_match_stats(force_cache=force_cache)
    raise ValueError()
