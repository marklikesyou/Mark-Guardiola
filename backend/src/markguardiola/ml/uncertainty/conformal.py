from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class PredictionInterval:
    lower: FloatArray
    upper: FloatArray
    coverage: float


class SplitConformalInterval:
    def __init__(
        self,
        *,
        coverage: float = 0.8,
        lower_bound: float | None = None,
        upper_bound: float | None = None,
    ) -> None:
        if not 0 < coverage < 1:
            raise ValueError()
        self.coverage = coverage
        self.lower_bound = lower_bound
        self.upper_bound = upper_bound
        self.radius_: float | None = None

    def fit(self, y_true: FloatArray, predictions: FloatArray) -> SplitConformalInterval:
        residuals = np.abs(np.asarray(y_true, dtype=float) - np.asarray(predictions, dtype=float))
        if residuals.size == 0:
            raise ValueError()
        quantile = min(1.0, np.ceil((residuals.size + 1) * self.coverage) / residuals.size)
        self.radius_ = float(np.quantile(residuals, quantile, method="higher"))
        return self

    def predict(self, predictions: FloatArray) -> PredictionInterval:
        if self.radius_ is None:
            raise RuntimeError()
        values = np.asarray(predictions, dtype=float)
        lower = values - self.radius_
        upper = values + self.radius_
        if self.lower_bound is not None:
            lower = np.maximum(lower, self.lower_bound)
        if self.upper_bound is not None:
            upper = np.minimum(upper, self.upper_bound)
        return PredictionInterval(lower=lower, upper=upper, coverage=self.coverage)
