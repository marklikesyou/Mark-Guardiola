from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from markguardiola.ml.evaluation.metrics import (
    count_metrics,
    probability_metrics,
    regression_metrics,
)


def subgroup_promotion_check(
    target: NDArray[np.float64],
    predictions: NDArray[np.float64],
    baseline_predictions: NDArray[np.float64],
    groups: NDArray[np.str_] | None,
    *,
    kind: str,
    minimum_gate_size: int = 100,
    maximum_relative_degradation: float = 0.25,
) -> tuple[dict[str, dict[str, float]], bool]:
    if groups is None:
        return {}, True
    if groups.shape != target.shape:
        raise ValueError()
    metric_fn, primary = {
        "probability": (probability_metrics, "log_loss"),
        "count": (count_metrics, "poisson_deviance"),
        "regression": (regression_metrics, "mae"),
    }[kind]
    reports: dict[str, dict[str, float]] = {}
    passed = True
    for group in sorted(np.unique(groups)):
        mask = groups == group
        count = int(np.count_nonzero(mask))
        if count < 20:
            continue
        metrics = metric_fn(target[mask], predictions[mask])
        baseline = metric_fn(target[mask], baseline_predictions[mask])[primary]
        group_passed = metrics[primary] <= max(baseline, 1e-7) * (1 + maximum_relative_degradation)
        if count >= minimum_gate_size and not group_passed:
            passed = False
        reports[str(group)] = {
            **metrics,
            f"baseline_{primary}": baseline,
            "sample_count": float(count),
            "promotion_gate_applies": float(count >= minimum_gate_size),
            "promotion_gate_passed": float(group_passed),
        }
    return reports, passed
