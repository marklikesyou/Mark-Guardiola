from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from markguardiola.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class DataSource(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "data_sources"

    key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    base_url: Mapped[str | None] = mapped_column(Text)
    adapter_version: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    capabilities: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    config: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)


class SchemaVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "schema_versions"
    __table_args__ = (UniqueConstraint("source_id", "entity_name", "version"),)

    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("data_sources.id"), nullable=False)
    entity_name: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    fields: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)


class IngestionRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ingestion_runs"

    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("data_sources.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requested_scope: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    source_revision: Mapped[str | None] = mapped_column(String(160))
    code_revision: Mapped[str | None] = mapped_column(String(64))
    records_seen: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    records_written: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    records_rejected: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    manifest: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)


class RawObject(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "raw_objects"
    __table_args__ = (
        UniqueConstraint("source_id", "content_sha256"),
        Index("ix_raw_objects_ingestion_run", "ingestion_run_id"),
    )

    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("data_sources.id"), nullable=False)
    ingestion_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ingestion_runs.id"), nullable=False
    )
    schema_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("schema_versions.id"))
    provider_object_id: Mapped[str | None] = mapped_column(String(512))
    request_url: Mapped[str | None] = mapped_column(Text)
    request_params: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    media_type: Mapped[str] = mapped_column(String(128), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    content_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    http_metadata: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)


class ProviderEntityMap(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "provider_entity_map"
    __table_args__ = (
        UniqueConstraint("source_id", "entity_type", "provider_entity_id"),
        Index("ix_provider_entity_canonical", "entity_type", "canonical_entity_id"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
    )

    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("data_sources.id"), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_entity_id: Mapped[str] = mapped_column(String(256), nullable=False)
    canonical_entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(256), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    mapping_method: Mapped[str] = mapped_column(String(32), nullable=False)
    manually_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DataQualityIssue(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "data_quality_issues"
    __table_args__ = (Index("ix_quality_run_severity", "ingestion_run_id", "severity"),)

    ingestion_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ingestion_runs.id"))
    source_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("data_sources.id"))
    rule_key: Mapped[str] = mapped_column(String(128), nullable=False)
    severity: Mapped[str] = mapped_column(String(24), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(64))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    provider_record_id: Mapped[str | None] = mapped_column(String(256))
    message: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution: Mapped[str | None] = mapped_column(Text)


class Competition(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "competitions"
    __table_args__ = (UniqueConstraint("country_code", "name"),)

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    country_code: Mapped[str] = mapped_column(String(3), nullable=False)
    competition_type: Mapped[str] = mapped_column(String(32), nullable=False, default="league")
    gender: Mapped[str] = mapped_column(String(16), nullable=False, default="male")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Season(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "seasons"
    __table_args__ = (UniqueConstraint("competition_id", "label"),)

    competition_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("competitions.id"), nullable=False)
    label: Mapped[str] = mapped_column(String(32), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Team(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "teams"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    short_name: Mapped[str | None] = mapped_column(String(64))
    country_code: Mapped[str | None] = mapped_column(String(3))
    founded_year: Mapped[int | None] = mapped_column(SmallInteger)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Player(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "players"
    __table_args__ = (
        Index("ix_players_identity", "normalized_name", "date_of_birth"),
        CheckConstraint("photo_url IS NULL OR photo_url LIKE 'https://%'", name="photo_url_https"),
    )

    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(200), nullable=False)
    given_name: Mapped[str | None] = mapped_column(String(100))
    family_name: Mapped[str | None] = mapped_column(String(100))
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    nationality_code: Mapped[str | None] = mapped_column(String(3))
    primary_position: Mapped[str | None] = mapped_column(String(32))
    preferred_foot: Mapped[str | None] = mapped_column(String(16))
    height_cm: Mapped[int | None] = mapped_column(SmallInteger)
    photo_url: Mapped[str | None] = mapped_column(Text)
    photo_provenance: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Coach(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "coaches"

    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    nationality_code: Mapped[str | None] = mapped_column(String(3))


class Referee(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "referees"

    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    nationality_code: Mapped[str | None] = mapped_column(String(3))


class Venue(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "venues"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    city: Mapped[str | None] = mapped_column(String(120))
    country_code: Mapped[str | None] = mapped_column(String(3))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    capacity: Mapped[int | None] = mapped_column(Integer)


class PlayerTeamPeriod(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "player_team_periods"
    __table_args__ = (
        UniqueConstraint("player_id", "team_id", "valid_from"),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="valid_dates"),
    )

    player_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("players.id"), nullable=False)
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id"), nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)
    squad_number: Mapped[int | None] = mapped_column(SmallInteger)
    position: Mapped[str | None] = mapped_column(String(32))
    available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evidence: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)


class Match(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "matches"
    result_provenance: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    __table_args__ = (
        UniqueConstraint("season_id", "home_team_id", "away_team_id", "kickoff_at"),
        CheckConstraint("home_team_id <> away_team_id", name="different_teams"),
        CheckConstraint(
            "kickoff_precision IN ('unknown', 'date', 'minute')", name="kickoff_precision"
        ),
        Index("ix_matches_kickoff", "kickoff_at"),
    )

    season_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("seasons.id"), nullable=False)
    home_team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id"), nullable=False)
    away_team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id"), nullable=False)
    venue_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("venues.id"))
    referee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("referees.id"))
    referee_available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    home_coach_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("coaches.id"))
    away_coach_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("coaches.id"))
    kickoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    kickoff_precision: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")
    kickoff_provenance: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    matchweek: Mapped[int | None] = mapped_column(SmallInteger)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    home_score: Mapped[int | None] = mapped_column(SmallInteger)
    away_score: Mapped[int | None] = mapped_column(SmallInteger)
    home_score_extra: Mapped[int | None] = mapped_column(SmallInteger)
    away_score_extra: Mapped[int | None] = mapped_column(SmallInteger)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ProvenanceMixin:
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("data_sources.id"), nullable=False)
    ingestion_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ingestion_runs.id"), nullable=False
    )
    schema_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("schema_versions.id"))
    source_record_id: Mapped[str] = mapped_column(String(512), nullable=False)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    field_provenance: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)


class Lineup(UUIDPrimaryKeyMixin, ProvenanceMixin, Base):
    __tablename__ = "lineups"
    __table_args__ = (UniqueConstraint("source_id", "source_record_id"),)

    match_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("matches.id"), nullable=False)
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id"), nullable=False)
    player_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("players.id"), nullable=False)
    is_starting: Mapped[bool] = mapped_column(Boolean, nullable=False)
    shirt_number: Mapped[int | None] = mapped_column(SmallInteger)
    position: Mapped[str | None] = mapped_column(String(32))
    formation_slot: Mapped[str | None] = mapped_column(String(32))


class PlayerMatchStat(UUIDPrimaryKeyMixin, ProvenanceMixin, Base):
    __tablename__ = "player_match_stats"
    __table_args__ = (
        UniqueConstraint("source_id", "source_record_id"),
        Index("ix_player_stats_match_player", "match_id", "player_id"),
        CheckConstraint("minutes >= 0 AND minutes <= 130", name="valid_minutes"),
    )

    match_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("matches.id"), nullable=False)
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id"), nullable=False)
    player_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("players.id"), nullable=False)
    minutes: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    started: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    football_position: Mapped[str | None] = mapped_column(String(32))
    stats: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)


class TeamMatchStat(UUIDPrimaryKeyMixin, ProvenanceMixin, Base):
    __tablename__ = "team_match_stats"
    __table_args__ = (
        UniqueConstraint("source_id", "source_record_id"),
        Index("ix_team_stats_match_team", "match_id", "team_id"),
    )

    match_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("matches.id"), nullable=False)
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id"), nullable=False)
    opponent_team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id"), nullable=False)
    is_home: Mapped[bool] = mapped_column(Boolean, nullable=False)
    stats: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)


class TeamStandingSnapshot(UUIDPrimaryKeyMixin, ProvenanceMixin, Base):
    __tablename__ = "team_standing_snapshots"
    __table_args__ = (
        UniqueConstraint("source_id", "source_record_id"),
        Index("ix_standings_team_available", "team_id", "available_at"),
    )

    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id"), nullable=False)
    season_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("seasons.id"), nullable=False)
    table_type: Mapped[str] = mapped_column(String(64), nullable=False)
    rank: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    played: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    points: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    won: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    drawn: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    lost: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    goals_for: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    goals_against: Mapped[int] = mapped_column(SmallInteger, nullable=False)


class Event(UUIDPrimaryKeyMixin, ProvenanceMixin, Base):
    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint("source_id", "source_record_id"),
        Index("ix_events_match_period_second", "match_id", "period", "second"),
    )

    match_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("matches.id"), nullable=False)
    team_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("teams.id"))
    player_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("players.id"))
    related_player_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("players.id"))
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    event_subtype: Mapped[str | None] = mapped_column(String(96))
    period: Mapped[int | None] = mapped_column(SmallInteger)
    second: Mapped[int | None] = mapped_column(Integer)
    x: Mapped[float | None] = mapped_column(Float)
    y: Mapped[float | None] = mapped_column(Float)
    detail: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)


class Shot(UUIDPrimaryKeyMixin, ProvenanceMixin, Base):
    __tablename__ = "shots"
    __table_args__ = (UniqueConstraint("source_id", "source_record_id"),)

    match_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("matches.id"), nullable=False)
    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id"), nullable=False)
    player_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("players.id"), nullable=False)
    assister_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("players.id"))
    minute: Mapped[int | None] = mapped_column(SmallInteger)
    x: Mapped[float | None] = mapped_column(Float)
    y: Mapped[float | None] = mapped_column(Float)
    xg: Mapped[float | None] = mapped_column(Float)
    result: Mapped[str | None] = mapped_column(String(64))
    situation: Mapped[str | None] = mapped_column(String(64))
    body_part: Mapped[str | None] = mapped_column(String(64))


class Injury(UUIDPrimaryKeyMixin, ProvenanceMixin, Base):
    __tablename__ = "injuries"
    __table_args__ = (UniqueConstraint("source_id", "source_record_id"),)

    player_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("players.id"), nullable=False)
    team_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("teams.id"))
    injury_type: Mapped[str | None] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    started_on: Mapped[date | None] = mapped_column(Date)
    expected_return_on: Mapped[date | None] = mapped_column(Date)
    ended_on: Mapped[date | None] = mapped_column(Date)
    certainty: Mapped[float | None] = mapped_column(Float)


class Suspension(UUIDPrimaryKeyMixin, ProvenanceMixin, Base):
    __tablename__ = "suspensions"
    __table_args__ = (UniqueConstraint("source_id", "source_record_id"),)

    player_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("players.id"), nullable=False)
    team_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("teams.id"))
    reason: Mapped[str | None] = mapped_column(String(160))
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date | None] = mapped_column(Date)
    match_count: Mapped[int | None] = mapped_column(SmallInteger)


class Transfer(UUIDPrimaryKeyMixin, ProvenanceMixin, Base):
    __tablename__ = "transfers"
    __table_args__ = (UniqueConstraint("source_id", "source_record_id"),)

    player_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("players.id"), nullable=False)
    from_team_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("teams.id"))
    to_team_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("teams.id"))
    transfer_date: Mapped[date] = mapped_column(Date, nullable=False)
    transfer_type: Mapped[str | None] = mapped_column(String(64))
    fee_eur: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))


class OddsSnapshot(UUIDPrimaryKeyMixin, ProvenanceMixin, Base):
    __tablename__ = "odds_snapshots"
    __table_args__ = (
        UniqueConstraint("source_id", "source_record_id"),
        Index("ix_odds_match_available", "match_id", "available_at"),
    )

    match_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("matches.id"), nullable=False)
    bookmaker: Mapped[str] = mapped_column(String(128), nullable=False)
    market: Mapped[str] = mapped_column(String(128), nullable=False)
    selection: Mapped[str] = mapped_column(String(128), nullable=False)
    decimal_odds: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    local_identity: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    password_hash: Mapped[str | None] = mapped_column(Text)


class League(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "leagues"

    owner_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    competition_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("competitions.id"))
    season_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("seasons.id"))
    head_to_head_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Europe/Rome")


class LeagueRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "league_rules"
    __table_args__ = (UniqueConstraint("league_id", "version"),)

    league_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leagues.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scoring: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    formations: Mapped[list[object]] = mapped_column(JSONB, nullable=False)
    roster_constraints: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    substitution_rules: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class LeagueMember(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "league_members"
    __table_args__ = (UniqueConstraint("league_id", "user_id"),)

    league_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leagues.id"), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    is_owner: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class FantasyTeam(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "fantasy_teams"
    __table_args__ = (UniqueConstraint("league_id", "name"),)

    league_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leagues.id"), nullable=False)
    member_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("league_members.id"))
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    is_user_team: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class PlayerFantasyRole(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "player_fantasy_roles"
    __table_args__ = (UniqueConstraint("league_id", "player_id", "role"),)

    league_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leagues.id"), nullable=False)
    player_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("players.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="canonical")


class RosterEntry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "roster_entries"
    __table_args__ = (UniqueConstraint("fantasy_team_id", "player_id"),)

    fantasy_team_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("fantasy_teams.id"), nullable=False
    )
    player_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("players.id"), nullable=False)
    acquired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    purchase_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    imported_name: Mapped[str | None] = mapped_column(String(256))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class MarketEntry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "market_entries"
    __table_args__ = (UniqueConstraint("league_id", "player_id"),)

    league_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leagues.id"), nullable=False)
    player_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("players.id"), nullable=False)
    available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    asking_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    imported_name: Mapped[str | None] = mapped_column(String(256))


class Budget(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "budgets"
    __table_args__ = (UniqueConstraint("fantasy_team_id", "effective_at"),)

    fantasy_team_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("fantasy_teams.id"), nullable=False
    )
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    total_credits: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    remaining_credits: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)


class Matchup(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "matchups"
    __table_args__ = (UniqueConstraint("league_id", "matchweek", "home_fantasy_team_id"),)

    league_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leagues.id"), nullable=False)
    matchweek: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    home_fantasy_team_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("fantasy_teams.id"), nullable=False
    )
    away_fantasy_team_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("fantasy_teams.id"), nullable=False
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FeatureSnapshotMetadata(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "feature_snapshot_metadata"
    __table_args__ = (
        UniqueConstraint("feature_schema_version", "prediction_cutoff", "manifest_hash"),
    )

    feature_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    prediction_cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    training_cutoff: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    row_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    dataset_manifest: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    feature_names: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)


class ModelVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "model_versions"
    __table_args__ = (UniqueConstraint("target", "version"),)

    target: Mapped[str] = mapped_column(String(96), nullable=False)
    version: Mapped[str] = mapped_column(String(96), nullable=False)
    algorithm: Mapped[str] = mapped_column(String(96), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    training_cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    feature_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    code_revision: Mapped[str | None] = mapped_column(String(64))
    artifact_path: Mapped[str] = mapped_column(Text, nullable=False)
    parameters: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    metrics: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    subgroup_metrics: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    calibration: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)


class PredictionRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "prediction_runs"

    prediction_cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    data_cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    model_versions: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    feature_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("feature_snapshot_metadata.id"), nullable=False
    )
    code_revision: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    simulation_priors: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )


class PlayerMatchPrediction(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "player_match_predictions"
    __table_args__ = (
        UniqueConstraint("prediction_run_id", "match_id", "player_id", "target"),
        CheckConstraint("reliability >= 0 AND reliability <= 1", name="reliability_range"),
    )

    prediction_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prediction_runs.id"), nullable=False
    )
    match_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("matches.id"), nullable=False)
    player_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("players.id"), nullable=False)
    target: Mapped[str] = mapped_column(String(96), nullable=False)
    expected_value: Mapped[float] = mapped_column(Float, nullable=False)
    median: Mapped[float] = mapped_column(Float, nullable=False)
    p10: Mapped[float] = mapped_column(Float, nullable=False)
    p90: Mapped[float] = mapped_column(Float, nullable=False)
    probability: Mapped[float | None] = mapped_column(Float)
    reliability: Mapped[float] = mapped_column(Float, nullable=False)
    distribution: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    model_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("model_versions.id"), nullable=False
    )


class SimulationRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "simulation_runs"

    prediction_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prediction_runs.id"), nullable=False
    )
    league_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("leagues.id"))
    simulation_count: Mapped[int] = mapped_column(Integer, nullable=False)
    seed: Mapped[int | None] = mapped_column(BigInteger)
    scoring_rule_version: Mapped[int | None] = mapped_column(Integer)
    parameters: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)


class LineupRecommendation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "lineup_recommendations"

    simulation_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("simulation_runs.id"), nullable=False
    )
    league_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leagues.id"), nullable=False)
    fantasy_team_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("fantasy_teams.id"), nullable=False
    )
    risk_mode: Mapped[str] = mapped_column(String(24), nullable=False)
    formation: Mapped[str] = mapped_column(String(64), nullable=False)
    starters: Mapped[list[object]] = mapped_column(JSONB, nullable=False)
    bench: Mapped[list[object]] = mapped_column(JSONB, nullable=False)
    expected_score: Mapped[float] = mapped_column(Float, nullable=False)
    median_score: Mapped[float] = mapped_column(Float, nullable=False)
    p10_score: Mapped[float] = mapped_column(Float, nullable=False)
    p90_score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    objective_value: Mapped[float] = mapped_column(Float, nullable=False)
    data_cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MarketRecommendation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "market_recommendations"

    simulation_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("simulation_runs.id"), nullable=False
    )
    league_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leagues.id"), nullable=False)
    fantasy_team_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("fantasy_teams.id"), nullable=False
    )
    target_player_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("players.id"), nullable=False)
    replace_player_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("players.id"))
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    horizon: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_improvement: Mapped[float] = mapped_column(Float, nullable=False)
    value_over_replacement: Mapped[float] = mapped_column(Float, nullable=False)
    budget_efficiency: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    detail: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)


class RecommendationExplanation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "recommendation_explanations"
    __table_args__ = (Index("ix_explanation_owner", "recommendation_type", "recommendation_id"),)

    recommendation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    recommendation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    rank: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)


class BackgroundJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "background_jobs"

    queue_job_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    job_type: Mapped[str] = mapped_column(String(96), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    parameters: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
