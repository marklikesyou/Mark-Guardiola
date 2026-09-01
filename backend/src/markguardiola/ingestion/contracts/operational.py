from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from markguardiola.ingestion.contracts.base import (
    CanonicalEventRecord,
    CanonicalLineupRecord,
    CanonicalMatchRecord,
    CanonicalPlayerIdentity,
    CanonicalPlayerMatchRecord,
)


class TeamIdentity(BaseModel):
    model_config = ConfigDict(frozen=True)
    provider_id: str
    name: str


class OperationalObservation(BaseModel):
    model_config = ConfigDict(frozen=True)
    source_record_id: str
    event_time: datetime
    available_at: datetime


class AvailabilityObservation(OperationalObservation):
    player_provider_id: str
    team_provider_id: str
    reason: str | None = None
    status: str
    suspended: bool = False
    starts_on: date
    ends_on: date | None = None


class TransferObservation(OperationalObservation):
    player_provider_id: str
    from_team: TeamIdentity | None = None
    to_team: TeamIdentity | None = None
    transfer_date: date
    transfer_type: str | None = None


class StandingObservation(OperationalObservation):
    team: TeamIdentity
    season_label: str
    table_type: str = "TOTAL"
    rank: int = Field(ge=1)
    played: int = Field(ge=0)
    points: int
    won: int = Field(ge=0)
    drawn: int = Field(ge=0)
    lost: int = Field(ge=0)
    goals_for: int = Field(ge=0)
    goals_against: int = Field(ge=0)


class OddsObservation(OperationalObservation):
    match_provider_id: str
    bookmaker: str
    market: str
    selection: str
    decimal_odds: float = Field(gt=1, allow_inf_nan=False)


class OperationalBatch(BaseModel):
    teams: list[TeamIdentity] = Field(default_factory=list)
    players: list[CanonicalPlayerIdentity] = Field(default_factory=list)
    matches: list[CanonicalMatchRecord] = Field(default_factory=list)
    player_stats: list[CanonicalPlayerMatchRecord] = Field(default_factory=list)
    lineups: list[CanonicalLineupRecord] = Field(default_factory=list)
    events: list[CanonicalEventRecord] = Field(default_factory=list)
    availability: list[AvailabilityObservation] = Field(default_factory=list)
    transfers: list[TransferObservation] = Field(default_factory=list)
    standings: list[StandingObservation] = Field(default_factory=list)
    odds: list[OddsObservation] = Field(default_factory=list)
