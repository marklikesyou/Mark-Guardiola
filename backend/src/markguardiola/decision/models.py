from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np
from numpy.typing import NDArray

from markguardiola.domain.enums import RiskMode

FloatArray = NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class FixtureDecisionProjection:
    fixture_id: str
    samples: FloatArray = field(compare=False, repr=False)
    appearance_samples: NDArray[np.bool_] = field(compare=False, repr=False)
    base_rating_samples: FloatArray = field(compare=False, repr=False)
    available: bool = True


@dataclass(frozen=True, slots=True)
class PlayerDecisionInput:
    player_id: str
    display_name: str
    roles: tuple[str, ...]
    expected_points: float
    median_points: float
    p10_points: float
    p90_points: float
    appearance_probability: float
    available: bool = True
    purchase_price: float | None = None
    horizon_points: dict[int, float] = field(default_factory=dict)
    samples: FloatArray | None = field(default=None, compare=False, repr=False)
    appearance_samples: NDArray[np.bool_] | None = field(default=None, compare=False, repr=False)
    base_rating_samples: FloatArray | None = field(default=None, compare=False, repr=False)
    scoring_role: str | None = None
    fixture_projections: tuple[FixtureDecisionProjection, ...] = field(
        default=(), compare=False, repr=False
    )
    photo_url: str | None = None


@dataclass(frozen=True, slots=True)
class SelectedPlayer:
    player_id: str
    display_name: str
    slot: str
    expected_points: float
    appearance_probability: float


@dataclass(frozen=True, slots=True)
class BenchPlayer:
    player_id: str
    display_name: str
    roles: tuple[str, ...]
    utility: float


@dataclass(frozen=True, slots=True)
class LineupDecision:
    formation: str
    risk_mode: RiskMode
    starters: tuple[SelectedPlayer, ...]
    bench: tuple[BenchPlayer, ...]
    objective_value: float
    expected_points: float
    p10_points: float
    p90_points: float
    score_samples: FloatArray | None = field(default=None, compare=False, repr=False)
    expected_substitutions: float = 0.0
    expected_modifier: float = 0.0
    optimization_method: str = "additive_cp_sat"
    evaluated_candidates: int = 1
    search_scenarios: int = 0


@dataclass(frozen=True, slots=True)
class MatchupDecision:
    lineup: LineupDecision
    win_probability: float
    draw_probability: float
    loss_probability: float
    scenario_count: int


@dataclass(frozen=True, slots=True)
class MarketCandidate:
    player: PlayerDecisionInput
    asking_price: float | None
    available: bool = True


@dataclass(frozen=True, slots=True)
class MarketRecommendationResult:
    target_player_id: str
    target_name: str
    replace_player_id: str
    replace_name: str
    price: float | None
    expected_improvement: float
    value_over_replacement: float
    budget_efficiency: float | None
    formation_before: str
    formation_after: str
    horizon_improvements: dict[int, float]
    role_flexibility_delta: int
    affordability: Literal["affordable", "unknown"] = "affordable"
    optimization_horizon: int = 1
    evaluation_method: str = "per_fixture_scenario_search"
    formation_schedule_before: tuple[str, ...] = ()
    formation_schedule_after: tuple[str, ...] = ()
