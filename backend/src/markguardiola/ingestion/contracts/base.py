from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from datetime import date, datetime
from typing import Any, Literal, Protocol
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator


class IngestionScope(BaseModel):
    model_config = ConfigDict(frozen=True)

    competition: str = "Serie A"
    competition_code: str = "SA"
    seasons: tuple[str, ...] = ()
    data_types: tuple[str, ...] = ()
    since: datetime | None = None
    until: datetime | None = None
    fixture_ids: tuple[str, ...] = ()
    team_ids: tuple[str, ...] = ()


class RawPayload(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    provider_object_id: str | None = None
    request_url: str
    request_params: dict[str, str | int | float | bool] = Field(default_factory=dict)
    media_type: str
    content: bytes
    event_time: datetime | None = None
    available_at: datetime
    retrieved_at: datetime
    response_headers: dict[str, str] = Field(default_factory=dict)
    schema_hint: str | None = None

    @field_validator("available_at", "retrieved_at", "event_time")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError()
        return value


class CanonicalMatchRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_record_id: str
    season_label: str
    competition_name: str
    kickoff_at: datetime
    kickoff_precision: Literal["date", "minute"] = "minute"
    kickoff_source_value: str | None = None
    kickoff_policy: str = "provider_timestamp"
    available_at: datetime
    home_team_provider_id: str
    home_team_name: str
    away_team_provider_id: str
    away_team_name: str
    status: str
    matchweek: int | None = None
    home_score: int | None = None
    away_score: int | None = None
    referee_provider_id: str | None = None
    referee_name: str | None = None
    venue_provider_id: str | None = None
    venue_name: str | None = None
    venue_city: str | None = None
    snapshot_key: str | None = None
    stats: dict[str, int | float | str | None] = Field(default_factory=dict)
    odds: dict[str, float] = Field(default_factory=dict)


class CanonicalPlayerMatchRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_record_id: str
    match_provider_id: str
    player_provider_id: str
    player_name: str
    team_provider_id: str
    team_name: str
    event_time: datetime
    available_at: datetime
    minutes: int = Field(ge=0, le=130)
    started: bool
    position: str | None = None
    stats: dict[str, int | float | str | None] = Field(default_factory=dict)


class CanonicalPlayerIdentity(BaseModel):
    model_config = ConfigDict(frozen=True)
    player_provider_id: str
    player_name: str
    available_at: datetime
    match_provider_id: str | None = None
    position: str | None = None
    date_of_birth: date | None = None
    given_name: str | None = None
    family_name: str | None = None
    team_provider_id: str | None = None
    team_name: str | None = None
    photo_url: str | None = None

    @field_validator("photo_url")
    @classmethod
    def require_secure_photo_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        parsed = urlsplit(normalized)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError()
        return normalized


class ProviderAdapter(Protocol):
    key: str
    name: str
    adapter_version: str
    base_url: str

    def iter_raw(self, scope: IngestionScope) -> AsyncIterator[RawPayload]: ...


class CanonicalFixtureFact(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_record_id: str
    match_provider_id: str
    team_provider_id: str | None = None
    player_provider_id: str | None = None

    available_at: datetime | None = None


class CanonicalLineupRecord(CanonicalFixtureFact):
    team_provider_id: str
    player_provider_id: str
    is_starting: bool
    shirt_number: int | None = None
    position: str | None = None
    formation_slot: str | None = None


class CanonicalShotRecord(CanonicalFixtureFact):
    team_provider_id: str
    player_provider_id: str
    minute: int | None = Field(default=None, ge=0, le=150)
    x: float | None = Field(default=None, ge=0, le=1)
    y: float | None = Field(default=None, ge=0, le=1)
    xg: float | None = Field(default=None, ge=0, le=1)
    result: str | None = None
    situation: str | None = None
    body_part: str | None = None


class CanonicalEventRecord(CanonicalFixtureFact):
    model_config = ConfigDict(frozen=True, allow_inf_nan=False)
    event_type: str
    event_subtype: str | None = None
    period: int | None = None
    second: int | None = Field(default=None, ge=0)
    x: float | None = None
    y: float | None = None
    detail: dict[str, object] = Field(default_factory=dict)


class MatchParser(Protocol):
    def parse_matches(self, payload: RawPayload) -> list[CanonicalMatchRecord]: ...


class JsonObject(Protocol):
    def __getitem__(self, key: str) -> Any: ...

    def get(self, key: str, default: Any = None) -> Any: ...

    def items(self) -> Any: ...


def string_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {str(key).lower(): str(value) for key, value in headers.items()}
