from __future__ import annotations

import csv
import io
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

from markguardiola.domain.timing import historical_result_available_at
from markguardiola.ingestion.adapters.http import CachePolicy, HttpAdapterClient
from markguardiola.ingestion.contracts import CanonicalMatchRecord, IngestionScope, RawPayload


class FootballDataCoUkAdapter:
    key = "football_data_co_uk"
    name = "Football-Data.co.uk"
    adapter_version = "1.0.0"
    base_url = "https://www.football-data.co.uk"

    def __init__(self, client: HttpAdapterClient) -> None:
        self._client = client

    async def iter_raw(self, scope: IngestionScope) -> AsyncIterator[RawPayload]:
        if not scope.seasons:
            raise ValueError()
        for season in scope.seasons:
            season_code = season_to_code(season)
            url = f"{self.base_url}/mmz4281/{season_code}/I1.csv"
            yield await self._client.get(
                url,
                cache_policy=_season_cache_policy(season),
                provider_object_id=f"serie-a-{season}",
                schema_hint=f"football-data-co-uk:I1:{season_code}",
            )

    @staticmethod
    def parse_matches(payload: RawPayload) -> list[CanonicalMatchRecord]:
        text = payload.content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        required = {"Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError()

        season_label = _season_from_provider_object(payload.provider_object_id)
        records: list[CanonicalMatchRecord] = []
        for row in reader:
            if not row.get("HomeTeam") or not row.get("AwayTeam"):
                continue
            kickoff = _parse_kickoff(row["Date"], row.get("Time"))
            source_id = f"{season_label}:{row['Date']}:{row['HomeTeam']}:{row['AwayTeam']}"
            stats = {
                canonical: _number(row.get(provider))
                for provider, canonical in _STAT_COLUMNS.items()
                if row.get(provider) not in {None, ""}
            }
            odds: dict[str, float] = {}
            for provider, canonical in _ODDS_COLUMNS.items():
                value = row.get(provider)
                if value:
                    odds[canonical] = float(value)
            records.append(
                CanonicalMatchRecord(
                    source_record_id=source_id,
                    season_label=season_label,
                    competition_name="Serie A",
                    kickoff_at=kickoff,
                    kickoff_precision="date",
                    kickoff_source_value=f"{row['Date']} {row.get('Time') or ''}".strip(),
                    kickoff_policy="calendar_date_unverified_timezone",
                    available_at=historical_result_available_at(kickoff, "date"),
                    home_team_provider_id=row["HomeTeam"],
                    home_team_name=row["HomeTeam"],
                    away_team_provider_id=row["AwayTeam"],
                    away_team_name=row["AwayTeam"],
                    status="finished",
                    home_score=int(row["FTHG"]),
                    away_score=int(row["FTAG"]),
                    referee_provider_id=row.get("Referee") or None,
                    referee_name=row.get("Referee") or None,
                    stats={key: value for key, value in stats.items() if value is not None},
                    odds=odds,
                )
            )
        return records


def season_to_code(season: str) -> str:
    normalized = season.strip().replace("/", "-")
    parts = normalized.split("-")
    if len(parts) != 2 or not all(part.isdigit() and len(part) == 4 for part in parts):
        raise ValueError()
    first, second = map(int, parts)
    if second != first + 1:
        raise ValueError()
    return f"{first % 100:02d}{second % 100:02d}"


def _season_from_provider_object(value: str | None) -> str:
    if not value or not value.startswith("serie-a-"):
        raise ValueError()
    return value.removeprefix("serie-a-")


def _parse_kickoff(date_value: str, time_value: str | None) -> datetime:
    formats = ("%d/%m/%Y %H:%M", "%d/%m/%y %H:%M", "%d/%m/%Y", "%d/%m/%y")
    combined = f"{date_value} {time_value}".strip() if time_value else date_value
    for fmt in formats:
        try:
            return datetime.strptime(combined, fmt).replace(hour=0, minute=0, tzinfo=UTC)
        except ValueError:
            continue
    raise ValueError()


def _number(value: str | None) -> int | float | None:
    if value in {None, ""}:
        return None
    assert value is not None
    numeric = float(value)
    return int(numeric) if numeric.is_integer() else numeric


def _season_cache_policy(season: str, *, now: datetime | None = None) -> CachePolicy:

    point = now or datetime.now(UTC)
    current_start_year = point.year if point.month >= 7 else point.year - 1
    ttl = timedelta(hours=6) if int(season[:4]) >= current_start_year else timedelta(days=30)
    return CachePolicy(ttl=ttl)


_STAT_COLUMNS = {
    "HS": "home_shots",
    "AS": "away_shots",
    "HST": "home_shots_on_target",
    "AST": "away_shots_on_target",
    "HC": "home_corners",
    "AC": "away_corners",
    "HF": "home_fouls",
    "AF": "away_fouls",
    "HY": "home_yellow_cards",
    "AY": "away_yellow_cards",
    "HR": "home_red_cards",
    "AR": "away_red_cards",
}

_ODDS_COLUMNS = {
    "B365H": "bet365_home",
    "B365D": "bet365_draw",
    "B365A": "bet365_away",
    "PSH": "pinnacle_home",
    "PSD": "pinnacle_draw",
    "PSA": "pinnacle_away",
    "AvgH": "market_average_home",
    "AvgD": "market_average_draw",
    "AvgA": "market_average_away",
}
