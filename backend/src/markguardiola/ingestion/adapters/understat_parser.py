from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta

import polars as pl

from markguardiola.ingestion.contracts import CanonicalMatchRecord, RawPayload


def parse_team_matches(payload: RawPayload) -> list[CanonicalMatchRecord]:
    if payload.schema_hint not in {
        "soccerdata-understat:team_match_stats",
        "soccerdata-understat:schedule",
    }:
        return []
    frame = pl.read_parquet(io.BytesIO(payload.content))
    required = {
        "game_id",
        "date",
        "home_team_id",
        "away_team_id",
        "home_team",
        "away_team",
        "home_goals",
        "away_goals",
        "home_xg",
        "away_xg",
    }
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError()
    start = int(payload.request_params["season_start"])
    result = []
    for row in frame.iter_rows(named=True):
        if row.get("season_id") is not None and int(row["season_id"]) != start:
            raise ValueError()
        played = bool(row.get("is_result", True))
        if played and (row["home_goals"] is None or row["away_goals"] is None):
            continue
        kickoff = row["date"]
        if not isinstance(kickoff, datetime):
            raise ValueError()
        kickoff = kickoff.replace(tzinfo=UTC) if kickoff.tzinfo is None else kickoff.astimezone(UTC)
        stats: dict[str, int | float | str | None] = {}
        for side, opposite in (("home", "away"), ("away", "home")) if played else ():
            for field in ("xg", "np_xg", "np_xg_difference", "ppda", "deep_completions"):
                value = row.get(f"{side}_{field}")
                if value is not None:
                    numeric = float(value)
                    if field in {"xg", "np_xg"} and not 0 <= numeric <= 20:
                        raise ValueError()
                    stats[f"{side}_{field}"] = numeric
            stats[f"{side}_xg_against"] = row[f"{opposite}_xg"]
        result.append(
            CanonicalMatchRecord(
                source_record_id=str(row["game_id"]),
                season_label=f"{start}-{start + 1}",
                competition_name="Serie A",
                kickoff_at=kickoff,
                available_at=kickoff + timedelta(hours=3) if played else payload.retrieved_at,
                home_team_provider_id=str(row["home_team_id"]),
                home_team_name=row["home_team"],
                away_team_provider_id=str(row["away_team_id"]),
                away_team_name=row["away_team"],
                status="finished" if played else "scheduled",
                home_score=int(row["home_goals"]) if played else None,
                away_score=int(row["away_goals"]) if played else None,
                stats=stats,
            )
        )
    return result
