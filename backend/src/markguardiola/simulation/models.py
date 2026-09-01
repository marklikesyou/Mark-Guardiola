from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
from numpy.typing import NDArray

IntArray = NDArray[np.int16]
BoolArray = NDArray[np.bool_]


@dataclass(frozen=True, slots=True)
class PlayerForecast:
    player_id: str
    team_id: str
    position: Literal["GK", "DEF", "MID", "FWD"]
    availability_probability: float
    start_probability: float
    appearance_probability: float
    expected_minutes: float
    minutes_stddev: float
    goal_weight: float
    assist_weight: float
    yellow_card_probability: float
    red_card_probability: float
    saves_per90: float = 0.0
    reliability: float = 1.0
    confirmed_start: bool | None = None
    penalty_weight: float = 0.0
    own_goal_weight: float = 0.0


@dataclass(frozen=True, slots=True)
class RareEventRates:
    penalty_goal_share: float
    own_goal_share: float
    missed_penalties_per_goal: float
    penalty_save_probability: float
    observed_matches: int
    observed_player_rows: int
    latest_available_at: str
    source_digest: str


@dataclass(frozen=True, slots=True)
class FixtureForecast:
    match_id: str
    home_team_id: str
    away_team_id: str
    home_goals_mean: float
    away_goals_mean: float
    players: tuple[PlayerForecast, ...]
    assisted_goal_probability: float = 0.72
    shared_goal_correlation: float = 0.08
    maximum_substitutions: int = 5
    rare_event_rates: RareEventRates | None = None


@dataclass(frozen=True, slots=True)
class PlayerSamples:
    player_id: str
    team_id: str
    started: BoolArray
    minutes: IntArray
    goals: IntArray
    assists: IntArray
    clean_sheet: BoolArray
    yellow_cards: IntArray
    red_cards: IntArray
    saves: IntArray
    goals_conceded: IntArray
    penalties_scored: IntArray
    penalties_missed: IntArray
    penalties_saved: IntArray
    own_goals: IntArray


@dataclass(frozen=True, slots=True)
class PlayerSimulationSummary:
    player_id: str
    mean_minutes: float
    median_minutes: float
    p10_minutes: float
    p90_minutes: float
    start_probability: float
    appearance_probability: float
    goal_probability: float
    assist_probability: float
    clean_sheet_probability: float
    yellow_card_probability: float
    red_card_probability: float
    mean_saves: float
    mean_goals_conceded: float
    mean_penalties_scored: float
    mean_penalties_missed: float
    mean_penalties_saved: float
    mean_own_goals: float


@dataclass(frozen=True, slots=True)
class FixtureSimulationResult:
    match_id: str
    simulation_count: int
    seed: int | None
    home_goals: IntArray
    away_goals: IntArray
    player_samples: dict[str, PlayerSamples]
    summaries: dict[str, PlayerSimulationSummary]
