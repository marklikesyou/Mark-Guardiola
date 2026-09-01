from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

FootballRole = Literal["GK", "DEF", "MID", "FWD"]


def _default_goal_points() -> dict[FootballRole, float]:
    return {"GK": 3.0, "DEF": 3.0, "MID": 3.0, "FWD": 3.0}


def _default_clean_sheet_points() -> dict[FootballRole, float]:
    return {"GK": 1.0, "DEF": 0.0, "MID": 0.0, "FWD": 0.0}


def _default_goal_conceded_points() -> dict[FootballRole, float]:
    return {"GK": -1.0, "DEF": 0.0, "MID": 0.0, "FWD": 0.0}


class ModifierBand(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    minimum_average: float = Field(ge=0, le=10)
    points: float


class ScoringRules(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    appearance_minimum_minutes: int = Field(default=1, ge=0, le=130)
    base_rating_enabled: bool = True
    base_rating_fallback: float = Field(default=6.0, ge=0, le=10)
    goal_points: dict[FootballRole, float] = Field(default_factory=_default_goal_points)
    assist_points: float = 1.0
    clean_sheet_points: dict[FootballRole, float] = Field(
        default_factory=_default_clean_sheet_points
    )
    goal_conceded_points: dict[FootballRole, float] = Field(
        default_factory=_default_goal_conceded_points
    )
    penalty_saved_points: float = 3.0
    penalty_missed_points: float = -3.0
    yellow_card_points: float = -0.5
    red_card_points: float = -1.0
    own_goal_points: float = -2.0
    save_points: float = 0.0
    defensive_modifier_enabled: bool = False
    defensive_modifier_roles: tuple[FootballRole, ...] = ("GK", "DEF")
    defensive_modifier_bands: tuple[ModifierBand, ...] = ()

    @model_validator(mode="after")
    def validate_modifier_bands(self) -> ScoringRules:
        for points in (self.goal_points, self.clean_sheet_points, self.goal_conceded_points):
            if set(points) != {"GK", "DEF", "MID", "FWD"}:
                raise ValueError()
        if len(set(self.defensive_modifier_roles)) != len(self.defensive_modifier_roles):
            raise ValueError()
        if self.defensive_modifier_enabled and not self.defensive_modifier_roles:
            raise ValueError()
        thresholds = [band.minimum_average for band in self.defensive_modifier_bands]
        if thresholds != sorted(set(thresholds)):
            raise ValueError()
        return self


class Formation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1, max_length=80, pattern=r"\S")
    slots: tuple[str, ...]

    @model_validator(mode="after")
    def eleven_legal_slots(self) -> Formation:
        if len(self.slots) != 11:
            raise ValueError()
        if len([slot for slot in self.slots if slot in {"GK", "Por"}]) != 1:
            raise ValueError()
        return self


class SubstitutionRules(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    maximum_substitutions: int = Field(default=5, ge=0, le=11)
    bench_size: int | None = Field(default=7, ge=0, le=50)
    allow_formation_change: bool = False


CLASSIC_FORMATIONS: tuple[Formation, ...] = (
    Formation(
        name="3-4-3",
        slots=("GK", "DEF", "DEF", "DEF", "MID", "MID", "MID", "MID", "FWD", "FWD", "FWD"),
    ),
    Formation(
        name="3-5-2",
        slots=("GK", "DEF", "DEF", "DEF", "MID", "MID", "MID", "MID", "MID", "FWD", "FWD"),
    ),
    Formation(
        name="4-3-3",
        slots=("GK", "DEF", "DEF", "DEF", "DEF", "MID", "MID", "MID", "FWD", "FWD", "FWD"),
    ),
    Formation(
        name="4-4-2",
        slots=("GK", "DEF", "DEF", "DEF", "DEF", "MID", "MID", "MID", "MID", "FWD", "FWD"),
    ),
    Formation(
        name="4-5-1",
        slots=("GK", "DEF", "DEF", "DEF", "DEF", "MID", "MID", "MID", "MID", "MID", "FWD"),
    ),
    Formation(
        name="5-3-2",
        slots=("GK", "DEF", "DEF", "DEF", "DEF", "DEF", "MID", "MID", "MID", "FWD", "FWD"),
    ),
    Formation(
        name="5-4-1",
        slots=("GK", "DEF", "DEF", "DEF", "DEF", "DEF", "MID", "MID", "MID", "MID", "FWD"),
    ),
)


DEFAULT_MANTRA_FORMATIONS: tuple[Formation, ...] = (
    Formation(name="4-3-3", slots=("Por", "Dd", "Dc", "Dc", "Ds", "M", "C", "C", "W", "A", "Pc")),
    Formation(name="4-2-3-1", slots=("Por", "Dd", "Dc", "Dc", "Ds", "M", "M", "W", "T", "W", "Pc")),
    Formation(name="3-4-2-1", slots=("Por", "Dc", "Dc", "Dc", "E", "M", "M", "E", "T", "A", "Pc")),
    Formation(name="3-5-2", slots=("Por", "Dc", "Dc", "Dc", "E", "M", "C", "C", "E", "A", "Pc")),
)
