from __future__ import annotations

import io
import re
from datetime import UTC, date, datetime, time
from typing import Any, Literal

import polars as pl

from markguardiola.domain.roles import football_role
from markguardiola.domain.timing import historical_result_available_at
from markguardiola.ingestion.contracts import (
    CanonicalMatchRecord,
    CanonicalPlayerMatchRecord,
    IngestionScope,
    RawPayload,
)


class PannadataParser:
    def parse_matches(
        self, payload: RawPayload, scope: IngestionScope
    ) -> list[CanonicalMatchRecord]:
        if "fixture" not in (payload.schema_hint or "").casefold():
            return []
        frame = _read_scoped_parquet(payload, scope)
        _require_columns(
            frame,
            {
                "match_id",
                "match_date",
                "home_team",
                "away_team",
                "home_team_id",
                "away_team_id",
                "match_status",
                "season",
            },
        )
        records: list[CanonicalMatchRecord] = []
        for row in frame.iter_rows(named=True):
            kickoff = _as_datetime(row["match_date"])
            precision: Literal["date", "minute"] = (
                "minute" if ":" in str(row["match_date"]) else "date"
            )
            played = str(row["match_status"]).casefold() in {"played", "finished", "ft"}
            available_at = (
                historical_result_available_at(kickoff, precision)
                if played
                else payload.available_at
            )
            records.append(
                CanonicalMatchRecord(
                    source_record_id=str(row["match_id"]),
                    season_label=str(row["season"]).replace("/", "-"),
                    competition_name="Serie A",
                    kickoff_at=kickoff,
                    kickoff_precision=precision,
                    kickoff_source_value=str(row["match_date"]),
                    kickoff_policy="provider_timestamp"
                    if precision == "minute"
                    else "utc_calendar_day",
                    available_at=available_at,
                    home_team_provider_id=str(row["home_team_id"]),
                    home_team_name=str(row["home_team"]),
                    away_team_provider_id=str(row["away_team_id"]),
                    away_team_name=str(row["away_team"]),
                    status="finished" if played else str(row["match_status"]).casefold(),
                    home_score=_optional_int(row.get("home_score")),
                    away_score=_optional_int(row.get("away_score")),
                )
            )
        return records

    def parse_player_matches(
        self, payload: RawPayload, scope: IngestionScope
    ) -> list[CanonicalPlayerMatchRecord]:
        hint = (payload.schema_hint or "").casefold()
        if "player" not in hint or "stat" not in hint:
            return []
        frame = _read_scoped_parquet(payload, scope)
        _require_columns(
            frame,
            {
                "match_id",
                "match_date",
                "player_id",
                "player_name",
                "team_id",
                "team_name",
                "mins_played",
            },
        )
        coverage_columns = [
            column
            for column in (
                "total_pass",
                "accurate_pass",
                "total_scoring_att",
                "total_tackle",
                "saves",
                "goals",
                "goal_assist",
                "yellow_card",
                "red_card",
            )
            if column in frame.columns
        ]
        frame = frame.with_columns(
            (
                pl.any_horizontal([pl.col(column).is_not_null() for column in coverage_columns])
                .any()
                .over("match_id")
                if coverage_columns
                else pl.lit(False)
            )
            .cast(pl.Int8)
            .alias("event_statistics_available")
        )
        stat_columns = [
            column for column in frame.columns if column not in _PLAYER_IDENTITY_COLUMNS
        ]
        records: list[CanonicalPlayerMatchRecord] = []
        for row in frame.iter_rows(named=True):
            event_time = _as_datetime(row["match_date"])
            stats = {
                _CANONICAL_STAT_NAMES.get(column, column): _json_scalar(row.get(column))
                for column in stat_columns
                if row.get(column) is not None
            }
            minutes = int(row["mins_played"] or 0)
            records.append(
                CanonicalPlayerMatchRecord(
                    source_record_id=f"{row['match_id']}:{row['player_id']}",
                    match_provider_id=str(row["match_id"]),
                    player_provider_id=str(row["player_id"]),
                    player_name=_player_name(row),
                    team_provider_id=str(row["team_id"]),
                    team_name=str(row["team_name"]),
                    event_time=event_time,
                    available_at=historical_result_available_at(
                        event_time, "minute" if ":" in str(row["match_date"]) else "date"
                    ),
                    minutes=minutes,
                    started=_started(row),
                    position=str(row["position"]) if row.get("position") else None,
                    stats=stats,
                )
            )
        return records


def _read_scoped_parquet(payload: RawPayload, scope: IngestionScope) -> pl.DataFrame:
    frame = pl.scan_parquet(io.BytesIO(payload.content))
    columns = frame.collect_schema().names()

    renamed: dict[str, str] = {}
    used_names = set(columns)
    for name in columns:
        normalized = re.sub(r"(?<!^)(?=[A-Z])", "_", name).casefold()
        if normalized != name and normalized in used_names:
            normalized = f"provider_{normalized}"
            if normalized in used_names:
                raise ValueError()
        renamed[name] = normalized
        used_names.add(normalized)
    frame = frame.rename(renamed)
    columns = list(renamed.values())
    if "competition" in columns:
        frame = frame.filter(
            pl.col("competition")
            .cast(pl.String)
            .str.to_lowercase()
            .is_in(["serie_a", "serie a", "ita"])
        )
    if scope.seasons and "season" in columns:
        normalized_seasons = [season.replace("/", "-") for season in scope.seasons]
        frame = frame.filter(
            pl.col("season").cast(pl.String).str.replace_all("/", "-").is_in(normalized_seasons)
        )
    return frame.collect()


def _require_columns(frame: pl.DataFrame, required: set[str]) -> None:
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError()


def _player_name(row: dict[str, Any]) -> str:
    full_name = " ".join(
        str(row[key]).strip() for key in ("first_name", "last_name") if row.get(key)
    )
    return full_name or str(row["player_name"])


def _as_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=value.tzinfo or UTC).astimezone(UTC)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=UTC)
    text = str(value)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}Z?", text):
        return datetime.combine(date.fromisoformat(text.removesuffix("Z")), time.min, tzinfo=UTC)
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=parsed.tzinfo or UTC).astimezone(UTC)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float, str)):
        return int(value)
    raise ValueError()


def _json_scalar(value: object) -> int | float | str | None:
    if value is None or isinstance(value, (int, float, str)):
        return value
    if isinstance(value, bool):
        return int(value)
    return str(value)


def _started(row: dict[str, Any]) -> bool:
    for column in ("is_starter", "started", "start", "game_started"):
        if column in row and row[column] is not None:
            return bool(row[column])

    return football_role(row.get("position")) is not None


_PLAYER_IDENTITY_COLUMNS = {
    "match_id",
    "match_date",
    "player_id",
    "player_name",
    "team_id",
    "team_name",
    "position",
    "mins_played",
    "competition",
    "season",
    "league",
}

_CANONICAL_STAT_NAMES = {
    "goal_assist": "assists",
    "total_scoring_att": "shots",
    "ontarget_scoring_att": "shots_on_target",
    "total_att_assist": "key_passes",
    "total_tackle": "tackles",
    "won_tackle": "tackles_won",
    "interception": "interceptions",
    "total_clearance": "clearances",
    "yellow_card": "yellow_cards",
    "red_card": "red_cards",
}
