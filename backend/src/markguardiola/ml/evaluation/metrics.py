from __future__ import annotations

from collections.abc import Mapping

import numpy as np
from numpy.typing import NDArray
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    log_loss,
    mean_absolute_error,
    mean_pinball_loss,
    mean_poisson_deviance,
    mean_squared_error,
)

FloatArray = NDArray[np.float64]


def expected_calibration_error(
    y_true: FloatArray, probabilities: FloatArray, bins: int = 10
) -> float:
    if bins < 2:
        raise ValueError()
    edges = np.linspace(0.0, 1.0, bins + 1)
    bucket = np.clip(np.digitize(probabilities, edges[1:-1]), 0, bins - 1)
    error = 0.0
    for index in range(bins):
        mask = bucket == index
        if not np.any(mask):
            continue
        error += float(np.mean(mask)) * abs(
            float(np.mean(probabilities[mask])) - float(np.mean(y_true[mask]))
        )
    return error


def probability_metrics(y_true: FloatArray, probabilities: FloatArray) -> dict[str, float]:
    clipped = np.clip(probabilities, 1e-7, 1 - 1e-7)
    metrics = {
        "log_loss": float(log_loss(y_true, clipped, labels=[0.0, 1.0])),
        "brier": float(brier_score_loss(y_true, clipped)),
        "calibration_error": expected_calibration_error(y_true, clipped),
    }
    metrics["pr_auc"] = (
        float(average_precision_score(y_true, clipped))
        if np.unique(y_true).size > 1
        else float(np.mean(y_true))
    )
    return metrics


def regression_metrics(y_true: FloatArray, predictions: FloatArray) -> dict[str, float]:
    return {
        "mae": float(mean_absolute_error(y_true, predictions)),
        "rmse": float(mean_squared_error(y_true, predictions) ** 0.5),
    }


def count_metrics(y_true: FloatArray, predictions: FloatArray) -> dict[str, float]:
    non_negative = np.clip(predictions, 1e-7, None)
    return {
        "poisson_deviance": float(mean_poisson_deviance(y_true, non_negative)),
        "mae": float(mean_absolute_error(y_true, non_negative)),
    }


def pinball_metrics(y_true: FloatArray, quantiles: Mapping[float, FloatArray]) -> dict[str, float]:
    return {
        f"pinball_{quantile:.2f}": float(mean_pinball_loss(y_true, predictions, alpha=quantile))
        for quantile, predictions in quantiles.items()
    }


def subgroup_probability_metrics(
    y_true: FloatArray,
    probabilities: FloatArray,
    groups: NDArray[np.str_],
    *,
    minimum_size: int = 20,
) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for group in sorted(np.unique(groups)):
        mask = groups == group
        if int(np.sum(mask)) >= minimum_size:
            result[str(group)] = probability_metrics(y_true[mask], probabilities[mask])
    return result
