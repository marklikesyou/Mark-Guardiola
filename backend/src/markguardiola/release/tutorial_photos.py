from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from markguardiola.core.config import Settings
from markguardiola.db.models import (
    DataSource,
    FantasyTeam,
    IngestionRun,
    League,
    Player,
    RosterEntry,
    SchemaVersion,
)
from markguardiola.db.session import get_session_factory
from markguardiola.entity_resolution.normalization import normalize_name
from markguardiola.ingestion.adapters.api_football import ApiFootballAdapter
from markguardiola.ingestion.adapters.http import FileResponseCache, HttpAdapterClient, json_payload
from markguardiola.ingestion.contracts import IngestionScope, RawPayload
from markguardiola.ingestion.pipelines.coordinator import IngestionCoordinator
from markguardiola.release.tutorial import TUTORIAL_LEAGUE_NAME

PHOTO_SEASON = 2024


@dataclass(frozen=True, slots=True)
class PhotoMatch:
    provider_player_id: str
    photo_url: str


class TutorialPhotoAdapter:
    key = "api_football_photos"
    name = "API-Football foto"
    adapter_version = ApiFootballAdapter.adapter_version
    base_url = ApiFootballAdapter.base_url

    def __init__(
        self,
        client: HttpAdapterClient,
        api_key: SecretStr,
        searches: tuple[str, ...],
        *,
        daily_limit: int,
        quota_ledger: Path,
    ) -> None:
        self._delegate = ApiFootballAdapter(
            client,
            api_key,
            daily_limit=daily_limit,
            quota_ledger=quota_ledger,
        )
        self._searches = searches

    async def iter_raw(self, scope: IngestionScope) -> AsyncIterator[RawPayload]:
        if scope.seasons != (f"{PHOTO_SEASON}-{PHOTO_SEASON + 1}",):
            raise ValueError()
        for search in self._searches:
            async for payload in self._delegate.search_players(
                season=PHOTO_SEASON,
                search=search,
            ):
                yield payload


class TutorialPhotoProcessor:
    def __init__(self, session: AsyncSession, players_by_search: dict[str, Player]) -> None:
        self._session = session
        self._players_by_search = players_by_search
        self.matched = 0

    async def __call__(
        self,
        source: DataSource,
        run: IngestionRun,
        schema: SchemaVersion,
        payload: RawPayload,
    ) -> int:
        search = str(payload.request_params.get("search", ""))
        target = self._players_by_search.get(search)
        if target is None:
            raise ValueError()
        body = json_payload(payload)
        if body.get("errors"):
            raise ValueError()
        rows = body.get("response")
        if not isinstance(rows, list):
            raise ValueError()
        match = best_photo_match(target.display_name, rows)
        if match is None:
            return 0
        target.photo_url = match.photo_url
        target.photo_provenance = {
            "source_id": str(source.id),
            "source": source.key,
            "provider_player_id": match.provider_player_id,
            "ingestion_run_id": str(run.id),
            "schema_version_id": str(schema.id),
            "available_at": payload.available_at.isoformat(),
            "matched_to": "tutorial_user_roster",
        }
        self.matched += 1
        await self._session.flush()
        return 1


async def enrich_tutorial_photos(settings: Settings) -> dict[str, object]:
    if settings.api_football_key is None:
        return {"status": "unavailable", "reason": "API-Football key is not configured"}
    async with get_session_factory()() as session:
        players = await _tutorial_players_without_photos(session)
        if not players:
            return {"status": "succeeded", "matched": 0, "requested": 0}
        players_by_search = _unique_searches(players)
        processor = TutorialPhotoProcessor(session, players_by_search)
        client = HttpAdapterClient(
            cache=FileResponseCache(settings.data_root / "raw" / ".http-cache")
        )
        run = await IngestionCoordinator(session, settings.data_root).ingest(
            TutorialPhotoAdapter(
                client,
                settings.api_football_key,
                tuple(players_by_search),
                daily_limit=settings.api_football_daily_limit,
                quota_ledger=settings.data_root / "raw" / ".quota" / "api-football.sqlite3",
            ),
            IngestionScope(
                seasons=(f"{PHOTO_SEASON}-{PHOTO_SEASON + 1}",),
                data_types=("tutorial_user_roster_photos",),
            ),
            processor=processor,
        )
        return {
            "status": "succeeded",
            "ingestion_run_id": str(run.id),
            "matched": processor.matched,
            "requested": len(players_by_search),
        }


def best_photo_match(target_name: str, rows: list[object]) -> PhotoMatch | None:
    target = normalize_name(target_name).split()
    scored: list[tuple[int, str, str]] = []
    for item in rows:
        if not isinstance(item, dict) or not isinstance(item.get("player"), dict):
            continue
        player = item["player"]
        provider_id = player.get("id")
        photo_url = player.get("photo")
        if provider_id is None or not isinstance(photo_url, str) or not _secure_url(photo_url):
            continue
        name = normalize_name(str(player.get("name") or "")).split()
        first = normalize_name(str(player.get("firstname") or "")).split()
        last = normalize_name(str(player.get("lastname") or "")).split()
        score = _name_score(target, name, first, last)
        if score >= 80:
            scored.append((score, str(provider_id), photo_url))
    if not scored:
        return None
    scored.sort(reverse=True)
    if len(scored) > 1 and scored[0][0] == scored[1][0]:
        return None
    return PhotoMatch(provider_player_id=scored[0][1], photo_url=scored[0][2])


def _name_score(
    target: list[str], provider_name: list[str], first: list[str], last: list[str]
) -> int:
    if target == provider_name:
        return 100
    first_initial = ""
    if first and first[0]:
        first_initial = first[0][0]
    elif provider_name:
        first_initial = provider_name[0][0]
    if not target or not first_initial or target[0][0] != first_initial:
        return 0
    if last and _contains_sequence(target, last):
        return 90
    if provider_name and len(provider_name) >= 2 and _contains_sequence(target, provider_name[1:]):
        return 80
    return 0


def _contains_sequence(haystack: list[str], needle: list[str]) -> bool:
    return bool(needle) and any(
        haystack[index : index + len(needle)] == needle
        for index in range(len(haystack) - len(needle) + 1)
    )


def _secure_url(value: str) -> bool:
    parsed = urlsplit(value.strip())
    return parsed.scheme == "https" and bool(parsed.netloc)


def _unique_searches(players: list[Player]) -> dict[str, Player]:
    result: dict[str, Player] = {}
    for player in players:
        tokens = normalize_name(player.display_name).split()
        candidates = [token for token in reversed(tokens) if len(token) >= 4]
        if not candidates:
            continue
        search = candidates[0]
        if search in result:
            continue
        result[search] = player
    return result


async def _tutorial_players_without_photos(session: AsyncSession) -> list[Player]:
    return list(
        (
            await session.scalars(
                select(Player)
                .join(RosterEntry, RosterEntry.player_id == Player.id)
                .join(FantasyTeam, FantasyTeam.id == RosterEntry.fantasy_team_id)
                .join(League, League.id == FantasyTeam.league_id)
                .where(
                    League.name == TUTORIAL_LEAGUE_NAME,
                    FantasyTeam.is_user_team.is_(True),
                    RosterEntry.active.is_(True),
                    Player.photo_url.is_(None),
                )
                .order_by(Player.display_name, Player.id)
            )
        ).all()
    )
