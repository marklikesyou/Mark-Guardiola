from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ProblemKind(StrEnum):
    PROBABILITY = "probability"
    COUNT = "count"
    REGRESSION = "regression"


@dataclass(frozen=True, slots=True)
class TargetDefinition:
    name: str
    kind: ProblemKind
    primary_metric: str
    calibration_required: bool
    lower_bound: float
    upper_bound: float | None = None


TARGETS: dict[str, TargetDefinition] = {
    item.name: item
    for item in (
        TargetDefinition("start_probability", ProblemKind.PROBABILITY, "log_loss", True, 0, 1),
        TargetDefinition("appearance_probability", ProblemKind.PROBABILITY, "log_loss", True, 0, 1),
        TargetDefinition("expected_minutes", ProblemKind.REGRESSION, "mae", False, 0, 130),
        TargetDefinition("goal_probability", ProblemKind.PROBABILITY, "log_loss", True, 0, 1),
        TargetDefinition("expected_goals", ProblemKind.COUNT, "poisson_deviance", False, 0),
        TargetDefinition("assist_probability", ProblemKind.PROBABILITY, "log_loss", True, 0, 1),
        TargetDefinition("expected_assists", ProblemKind.COUNT, "poisson_deviance", False, 0),
        TargetDefinition("team_goals", ProblemKind.COUNT, "poisson_deviance", False, 0),
        TargetDefinition("team_goals_conceded", ProblemKind.COUNT, "poisson_deviance", False, 0),
        TargetDefinition(
            "clean_sheet_probability", ProblemKind.PROBABILITY, "log_loss", True, 0, 1
        ),
        TargetDefinition("goalkeeper_saves", ProblemKind.COUNT, "poisson_deviance", False, 0),
        TargetDefinition(
            "goalkeeper_goals_conceded", ProblemKind.COUNT, "poisson_deviance", False, 0
        ),
        TargetDefinition(
            "yellow_card_probability", ProblemKind.PROBABILITY, "log_loss", True, 0, 1
        ),
        TargetDefinition("red_card_probability", ProblemKind.PROBABILITY, "log_loss", True, 0, 1),
        TargetDefinition("penalty_involvement", ProblemKind.PROBABILITY, "log_loss", True, 0, 1),
        TargetDefinition("base_rating", ProblemKind.REGRESSION, "mae", False, 0, 10),
    )
}


def target_definition(name: str) -> TargetDefinition:
    try:
        return TARGETS[name]
    except KeyError:
        raise KeyError() from None
