from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from markguardiola.domain.enums import JobStatus, KickoffPrecision, LeagueMode, RiskMode
from markguardiola.fantasy.roster import RosterConstraints, RosterValidation
from markguardiola.fantasy.rules import Formation, ScoringRules
from markguardiola.fantasy.rules.models import SubstitutionRules


class ApiContract(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PageMeta(ApiContract):
    limit: int
    offset: int
    total: int


class TeamSummary(ApiContract):
    id: uuid.UUID
    name: str
    short_name: str | None
    country_code: str | None


class TeamPage(ApiContract):
    items: list[TeamSummary]
    meta: PageMeta


class PlayerSummary(ApiContract):
    id: uuid.UUID
    display_name: str
    primary_position: str | None
    nationality_code: str | None
    photo_url: str | None = None
    photo_source: str | None = None
    active: bool


class PlayerDetail(PlayerSummary):
    date_of_birth: date | None
    preferred_foot: str | None
    height_cm: int | None
    current_team: TeamSummary | None = None


class PlayerPage(ApiContract):
    items: list[PlayerSummary]
    meta: PageMeta


class MatchSummary(ApiContract):
    id: uuid.UUID
    kickoff_at: datetime
    kickoff_precision: KickoffPrecision = Field(
        default=KickoffPrecision.UNKNOWN,
        description="Only minute precision identifies a kickoff clock. Date/unknown represents "
        "a UTC calendar day and must not be displayed as a confirmed time "
        "or shifted to another day.",
    )
    matchweek: int | None
    status: str
    home_team: TeamSummary
    away_team: TeamSummary
    home_score: int | None
    away_score: int | None


class MatchPage(ApiContract):
    items: list[MatchSummary]
    meta: PageMeta


class PlayerStatProvenance(ApiContract):
    stat_id: uuid.UUID
    source_id: uuid.UUID
    source_key: str
    source_name: str
    source_priority: int
    source_record_id: str
    ingestion_run_id: uuid.UUID
    schema_version_id: uuid.UUID | None
    adapter_version: str
    event_time: datetime
    available_at: datetime
    ingested_at: datetime
    field_provenance: dict[str, object]


class PlayerFormMatch(ApiContract):
    match_id: uuid.UUID
    kickoff_at: datetime
    kickoff_precision: KickoffPrecision = Field(
        default=KickoffPrecision.UNKNOWN,
        description="Only minute precision identifies a kickoff clock. Otherwise display the UTC "
        "calendar date without a time, preserving the source date in every viewing timezone.",
    )
    matchweek: int | None
    team: TeamSummary
    opponent: TeamSummary
    is_home: bool
    minutes: int
    started: bool
    goals: int | None
    assists: int | None
    shots: int | None
    xg: float | None
    xa: float | None
    base_rating: float | None
    field_sources: dict[str, uuid.UUID]
    sources: list[PlayerStatProvenance]


class PlayerRecentFormView(ApiContract):
    player_id: uuid.UUID
    as_of: datetime
    data_cutoff: datetime | None
    limit: int
    coverage: Literal["observed_player_matches"] = "observed_player_matches"
    items: list[PlayerFormMatch] = Field(
        description="Newest observed finished player matches first; missing matches are not zeroes."
    )
    warnings: tuple[str, ...] = ()


class LeagueCreate(ApiContract):
    name: str = Field(min_length=1, max_length=160)
    mode: LeagueMode
    owner_display_name: str = Field(default="Allenatore", min_length=1, max_length=160)
    local_identity: str = Field(default="local-owner", min_length=1, max_length=160)
    team_name: str = Field(default="La mia rosa", min_length=1, max_length=160)
    competition_id: uuid.UUID | None = None
    season_id: uuid.UUID | None = None
    head_to_head_enabled: bool = False
    timezone: str = "Europe/Rome"
    total_credits: Decimal = Field(default=Decimal("500"), ge=0)


class LeagueRulesWrite(ApiContract):
    scoring: ScoringRules = Field(default_factory=ScoringRules)
    formations: tuple[Formation, ...] | None = Field(default=None, min_length=1, max_length=100)
    roster_constraints: RosterConstraints = Field(default_factory=RosterConstraints)
    substitution_rules: SubstitutionRules = Field(default_factory=SubstitutionRules)


class LeagueRulesView(LeagueRulesWrite):
    version: int
    effective_from: datetime


class FantasyTeamView(ApiContract):
    id: uuid.UUID
    name: str
    is_user_team: bool
    remaining_credits: Decimal | None = None


class LeagueView(ApiContract):
    id: uuid.UUID
    name: str
    mode: LeagueMode
    owner_user_id: uuid.UUID
    competition_id: uuid.UUID | None
    season_id: uuid.UUID | None
    head_to_head_enabled: bool
    timezone: str
    rules: LeagueRulesView
    fantasy_teams: list[FantasyTeamView]


class LeagueSummary(ApiContract):
    id: uuid.UUID
    name: str
    mode: LeagueMode
    head_to_head_enabled: bool


class LeaguePage(ApiContract):
    items: list[LeagueSummary]
    meta: PageMeta


class LeagueSettingsWrite(ApiContract):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    head_to_head_enabled: bool | None = None


class BudgetWrite(ApiContract):
    remaining_credits: Decimal = Field(ge=0)


class BudgetView(BudgetWrite):
    fantasy_team_id: uuid.UUID
    total_credits: Decimal
    effective_at: datetime


class ImportPlayer(ApiContract):
    name: str = Field(min_length=1, max_length=200)
    player_id: uuid.UUID | None = None
    role: str | None = Field(default=None, max_length=16)
    team: str | None = Field(default=None, max_length=160)
    purchase_price: Decimal | None = Field(default=None, ge=0)


class RosterImportRequest(ApiContract):
    fantasy_team_id: uuid.UUID | None = None
    fantasy_team_name: str = Field(default="La mia rosa", min_length=1, max_length=160)
    is_user_team: bool = True
    replace_existing: bool = True
    players: list[ImportPlayer] = Field(min_length=1, max_length=500)
    remaining_credits: Decimal | None = Field(default=None, ge=0)


class MarketImportRequest(ApiContract):
    replace_existing: bool = True
    players: list[ImportPlayer] = Field(min_length=1, max_length=1000)


class ResolutionCandidateView(ApiContract):
    player_id: uuid.UUID
    display_name: str
    photo_url: str | None = None
    confidence: float
    evidence: tuple[str, ...]


class ImportResolutionView(ApiContract):
    imported_name: str
    status: Literal["resolved", "ambiguous", "unresolved"]
    selected_player_id: uuid.UUID | None
    confidence: float
    candidates: tuple[ResolutionCandidateView, ...]


class ImportResult(ApiContract):
    fantasy_team_id: uuid.UUID | None = None
    resolved_count: int
    unresolved_count: int
    resolutions: list[ImportResolutionView]


class RosterPlayerView(ApiContract):
    player_id: uuid.UUID
    display_name: str
    photo_url: str | None = None
    roles: tuple[str, ...]
    primary_position: str | None
    purchase_price: Decimal | None
    active: bool


class RosterView(ApiContract):
    fantasy_team: FantasyTeamView
    players: list[RosterPlayerView]
    validation: RosterValidation | None = None


class PredictionValue(ApiContract):
    target: str
    model_version: str
    expected_value: float
    median: float
    p10: float
    p90: float
    probability: float | None
    reliability: float


class PlayerFixturePrediction(ApiContract):
    player_id: uuid.UUID
    prediction_run_id: uuid.UUID
    match: MatchSummary
    prediction_cutoff: datetime
    data_cutoff: datetime
    values: list[PredictionValue]


class FixturePrediction(ApiContract):
    match: MatchSummary
    prediction_run_id: uuid.UUID
    prediction_cutoff: datetime
    data_cutoff: datetime
    players: list[PlayerFixturePrediction]


class LineupRecommendationRequest(ApiContract):
    fantasy_team_id: uuid.UUID | None = None
    risk_mode: RiskMode = RiskMode.BALANCED
    bench_size: int | None = Field(default=None, ge=0, le=30)

    @model_validator(mode="after")
    def reject_matchup_mode(self) -> LineupRecommendationRequest:
        if self.risk_mode == RiskMode.MATCHUP:
            raise ValueError()
        return self


class SelectedPlayerView(ApiContract):
    player_id: uuid.UUID
    display_name: str
    photo_url: str | None = None
    slot: str
    expected_points: float
    appearance_probability: float


class BenchPlayerView(ApiContract):
    player_id: uuid.UUID
    display_name: str
    photo_url: str | None = None
    roles: tuple[str, ...]
    utility: float


class ExplanationView(ApiContract):
    text: str
    evidence_key: str
    source_feature: str
    confidence: float


class PlayerOutlookRequest(ApiContract):
    horizon: int = Field(default=1, ge=1, le=10)


class PlayerRecommendationScore(ApiContract):
    value: float = Field(
        description=(
            "Mean individual fantasy points in the next fixture under the active league rules. "
            "Not a 0-100 rating, a probability, or a guarantee of selection in a legal XI. "
            "Lineup-level modifiers and substitutions are excluded."
        )
    )
    unit: Literal["fantasy_points"] = "fantasy_points"
    objective: Literal["expected_points"] = "expected_points"
    scope: Literal["individual_next_fixture"] = "individual_next_fixture"


class PlayerFootballOutlook(ApiContract):
    mean_minutes: float
    median_minutes: float
    p10_minutes: float
    p90_minutes: float
    start_probability: float
    appearance_probability: float
    goal_probability: float
    assist_probability: float
    clean_sheet_probability: float = Field(
        description=(
            "Probability of at least 60 player minutes and zero team goals conceded "
            "in the simulated fixture."
        )
    )
    mean_saves: float
    mean_goals_conceded: float


class PlayerFixtureOutlook(ApiContract):
    match: MatchSummary
    expected_points: float
    median_points: float
    p10_points: float
    p90_points: float
    available: bool
    scoring_appearance_probability: float = Field(
        description=(
            "Probability of positive minutes meeting the league's appearance_minimum_minutes."
        )
    )
    confidence: float
    football: PlayerFootballOutlook
    explanations: tuple[ExplanationView, ...]


class PlayerOutlookView(ApiContract):
    player_id: uuid.UUID
    league_id: uuid.UUID
    rules_version: int
    roles: tuple[str, ...]
    scoring_role: str | None
    recommendation_score: PlayerRecommendationScore
    requested_horizon: int
    fixtures: list[PlayerFixtureOutlook]
    prediction_run_id: uuid.UUID
    model_versions: dict[str, str]
    prediction_cutoff: datetime
    data_cutoff: datetime
    decision_cutoff: datetime
    simulation_count: int
    seed: int
    warnings: tuple[str, ...] = ()


class LineupRecommendationView(ApiContract):
    recommendation_id: uuid.UUID
    fantasy_team_id: uuid.UUID
    formation: str
    risk_mode: RiskMode
    starters: tuple[SelectedPlayerView, ...]
    bench: tuple[BenchPlayerView, ...]
    expected_points: float
    p10_points: float
    p90_points: float
    confidence: float
    data_cutoff: datetime
    decision_cutoff: datetime
    explanations: tuple[ExplanationView, ...]
    expected_substitutions: float = 0.0
    expected_modifier: float = 0.0
    optimization_method: str = "scenario_beam_search"
    evaluated_candidates: int = 1
    search_scenarios: int = 0
    global_optimality_proven: bool = False
    warnings: tuple[str, ...] = ()


class MarketRecommendationRequest(ApiContract):
    fantasy_team_id: uuid.UUID | None = None
    limit: int = Field(default=20, ge=1, le=100)
    recover_purchase_price: bool = False
    horizon: Literal[1, 3, 5, 10] = 1


class MarketRecommendationItem(ApiContract):
    recommendation_id: uuid.UUID
    target_player_id: uuid.UUID
    target_name: str
    target_photo_url: str | None = None
    replace_player_id: uuid.UUID
    replace_name: str
    replace_photo_url: str | None = None
    asking_price: float | None
    expected_improvement: float
    value_over_replacement: float
    budget_efficiency: float | None
    formation_before: str
    formation_after: str
    horizon_improvements: dict[int, float]
    role_flexibility_delta: int
    confidence: float
    explanations: tuple[ExplanationView, ...]
    affordability: Literal["affordable", "unknown"] = "affordable"
    optimization_horizon: int = 1
    evaluation_method: str = "per_fixture_scenario_search"
    formation_schedule_before: tuple[str, ...] = ()
    formation_schedule_after: tuple[str, ...] = ()
    global_optimality_proven: bool = False


class MarketRecommendationView(ApiContract):
    fantasy_team_id: uuid.UUID
    remaining_budget: float | None
    data_cutoff: datetime
    decision_cutoff: datetime
    items: list[MarketRecommendationItem]
    warnings: tuple[str, ...] = ()


class MatchupRecommendationRequest(ApiContract):
    fantasy_team_id: uuid.UUID | None = None
    opponent_fantasy_team_id: uuid.UUID
    simulation_count: int = Field(default=2000, ge=100, le=100_000)
    seed: int = 2026


class MatchupRecommendationView(ApiContract):
    lineup: LineupRecommendationView
    opponent_fantasy_team_id: uuid.UUID
    win_probability: float
    draw_probability: float
    loss_probability: float
    simulation_count: int


class JobCreate(ApiContract):
    parameters: dict[str, object] = Field(default_factory=dict)


class JobView(ApiContract):
    id: uuid.UUID
    queue_job_id: str | None
    job_type: str
    status: JobStatus
    parameters: dict[str, object]
    progress: float
    queued_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    result: dict[str, object] | None
    error: str | None


class FreshnessView(ApiContract):
    latest_successful_ingestion: datetime | None
    latest_prediction_cutoff: datetime | None
    latest_model_training: datetime | None


class SourceStatusView(ApiContract):
    key: str
    name: str
    status: Literal["available", "stale", "failed", "unconfigured", "unavailable"]
    latest_observation: datetime | None
    latest_successful_ingestion: datetime | None
    latest_attempt_status: str | None
    capabilities: tuple[str, ...]


class SystemStatusView(ApiContract):
    status: Literal["healthy", "updating", "degraded"]
    freshness: FreshnessView
    unresolved_quality_issues: int
    unresolved_blocking_issues: int
    champion_models: int
    queued_jobs: int
    running_jobs: int
    warnings: list[str]
    notices: list[str] = Field(default_factory=list)
    sources: list[SourceStatusView] = Field(default_factory=list)
    incompatible_champion_models: int = 0
    upcoming_fixture_count: int = 0
