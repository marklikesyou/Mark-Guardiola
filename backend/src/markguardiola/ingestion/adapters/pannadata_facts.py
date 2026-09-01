from __future__ import annotations

import json
from collections.abc import Iterator

from markguardiola.domain.roles import football_role
from markguardiola.ingestion.adapters.pannadata_parser import (
    _optional_int,
    _read_scoped_parquet,
    _require_columns,
)
from markguardiola.ingestion.contracts.base import (
    CanonicalEventRecord,
    CanonicalLineupRecord,
    CanonicalShotRecord,
    IngestionScope,
    RawPayload,
)


def parse_lineups(payload: RawPayload, scope: IngestionScope) -> Iterator[CanonicalLineupRecord]:
    if "opta_lineups.parquet" not in (payload.schema_hint or ""):
        return
    frame = _read_scoped_parquet(payload, scope)
    _require_columns(frame, {"match_id", "team_id", "player_id", "is_starter"})
    for row in frame.iter_rows(named=True):
        yield CanonicalLineupRecord(
            source_record_id=f"lineup:{row['match_id']}:{row['player_id']}",
            match_provider_id=row["match_id"],
            team_provider_id=row["team_id"],
            player_provider_id=row["player_id"],
            is_starting=row["is_starter"],
            shirt_number=_optional_int(row.get("shirt_number")),
            position=football_role(row.get("position")),
            formation_slot=row.get("formation_place"),
        )


def parse_shots(payload: RawPayload, scope: IngestionScope) -> Iterator[CanonicalShotRecord]:
    if "opta_shot_events.parquet" not in (payload.schema_hint or ""):
        return
    frame = _read_scoped_parquet(payload, scope)
    _require_columns(frame, {"match_id", "event_id", "team_id", "player_id", "is_goal"})
    for row in frame.iter_rows(named=True):
        if row.get("is_own_goal"):
            continue
        yield CanonicalShotRecord(
            source_record_id=f"shot:{row['match_id']}:{row['event_id']}",
            match_provider_id=row["match_id"],
            team_provider_id=row["team_id"],
            player_provider_id=row["player_id"],
            minute=_optional_int(row.get("minute")),
            x=_coordinate(row.get("x")),
            y=_coordinate(row.get("y")),
            xg=row.get("xg"),
            result="goal" if row["is_goal"] else "blocked" if row.get("is_blocked") else "non_goal",
            situation=row.get("situation"),
            body_part=row.get("body_part"),
        )


def parse_events(payload: RawPayload, scope: IngestionScope) -> Iterator[CanonicalEventRecord]:
    if "events_serie_a.parquet" not in (payload.schema_hint or "").casefold():
        return
    frame = _read_scoped_parquet(payload, scope)
    _require_columns(frame, {"match_id", "event_id", "type_id", "minute", "second"})
    for row in frame.iter_rows(named=True):
        qualifiers = json.loads(row["qualifier_json"]) if row.get("qualifier_json") else {}
        event_type = _EVENT_TYPES.get(row["type_id"], "unclassified")
        if event_type == "goal" and "28" in qualifiers:
            event_type = "own_goal"
        yield CanonicalEventRecord(
            source_record_id=f"event:{row['match_id']}:{row['event_id']}",
            match_provider_id=row["match_id"],
            team_provider_id=row.get("team_id") or None,
            player_provider_id=row.get("player_id") or None,
            event_type=event_type,
            period=_optional_int(row.get("period_id")),
            second=int(row["minute"] or 0) * 60 + int(row["second"] or 0),
            x=_coordinate(row.get("x")),
            y=_coordinate(row.get("y")),
            detail={
                "provider_type_id": row["type_id"],
                "outcome": row.get("outcome"),
                "end_x": _coordinate(row.get("end_x")),
                "end_y": _coordinate(row.get("end_y")),
                "qualifiers": qualifiers,
            },
        )


def _coordinate(value: float | None) -> float | None:
    return None if value is None else value / 100


_EVENT_TYPES = {
    1: "pass",
    2: "offside_pass",
    3: "dribble",
    4: "foul",
    5: "ball_out",
    6: "corner_awarded",
    7: "tackle",
    8: "interception",
    9: "turnover",
    10: "save",
    11: "claim",
    12: "clearance",
    13: "shot_missed",
    14: "shot_post",
    15: "shot_saved",
    16: "goal",
    17: "card",
    18: "substitution_off",
    19: "substitution_on",
    20: "player_retired",
    21: "player_returns",
    30: "period_end",
    32: "period_start",
    34: "lineup",
    35: "position_change",
    40: "formation_change",
    41: "punch",
    43: "deleted",
    44: "aerial_duel",
    45: "challenge",
    47: "card_rescinded",
    49: "ball_recovery",
    50: "dispossessed",
    51: "error",
    52: "goalkeeper_pickup",
    58: "penalty_faced",
    59: "goalkeeper_sweeper",
    61: "ball_touch",
    74: "blocked_pass",
    84: "deleted_after_review",
}
