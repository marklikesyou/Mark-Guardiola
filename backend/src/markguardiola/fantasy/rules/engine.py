from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
from numpy.typing import NDArray

from markguardiola.fantasy.rules.models import FootballRole, ScoringRules

FloatArray = NDArray[np.float64]


class FantasyScorer:
    def __init__(self, rules: ScoringRules) -> None:
        self.rules = rules

    def score(
        self,
        events: Mapping[str, float | int | bool | NDArray[np.generic]],
        *,
        role: FootballRole,
    ) -> FloatArray:
        minutes = _array(events.get("minutes", 0))
        size = minutes.size
        appeared = (minutes > 0) & (minutes >= self.rules.appearance_minimum_minutes)
        base_rating = _broadcast(events.get("base_rating", self.rules.base_rating_fallback), size)
        score = np.where(appeared, base_rating if self.rules.base_rating_enabled else 0.0, 0.0)
        score = score + _broadcast(events.get("goals", 0), size) * self.rules.goal_points[role]
        score = score + _broadcast(events.get("assists", 0), size) * self.rules.assist_points
        score = (
            score
            + _broadcast(events.get("clean_sheet", 0), size) * self.rules.clean_sheet_points[role]
        )
        score = (
            score
            + _broadcast(events.get("goals_conceded", 0), size)
            * self.rules.goal_conceded_points[role]
        )
        score = (
            score
            + _broadcast(events.get("penalties_saved", 0), size) * self.rules.penalty_saved_points
        )
        score = (
            score
            + _broadcast(events.get("penalties_missed", 0), size) * self.rules.penalty_missed_points
        )
        score = (
            score + _broadcast(events.get("yellow_cards", 0), size) * self.rules.yellow_card_points
        )
        score = score + _broadcast(events.get("red_cards", 0), size) * self.rules.red_card_points
        score = score + _broadcast(events.get("own_goals", 0), size) * self.rules.own_goal_points
        score = score + _broadcast(events.get("saves", 0), size) * self.rules.save_points
        return np.where(appeared, score, 0.0).astype(float)

    def defensive_modifier(
        self,
        *,
        lineup_roles: Sequence[FootballRole],
        base_ratings: Sequence[float],
    ) -> float:
        if not self.rules.defensive_modifier_enabled:
            return 0.0
        eligible = [
            rating
            for role, rating in zip(lineup_roles, base_ratings, strict=True)
            if role in self.rules.defensive_modifier_roles
        ]
        if not eligible:
            return 0.0
        average = float(np.mean(eligible))
        points = 0.0
        for band in self.rules.defensive_modifier_bands:
            if average >= band.minimum_average:
                points = band.points
        return points


def _array(value: object) -> FloatArray:
    array = np.asarray(value, dtype=float)
    return array.reshape(1) if array.ndim == 0 else array


def _broadcast(value: object, size: int) -> FloatArray:
    array = _array(value)
    if array.size == size:
        return array
    if array.size == 1:
        return np.full(size, float(array[0]), dtype=float)
    raise ValueError()
