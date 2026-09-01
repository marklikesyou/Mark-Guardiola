from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]


class PriorProbabilityEstimator:
    def __init__(self, smoothing: float = 1.0) -> None:
        self.smoothing = smoothing
        self.probability_: float | None = None

    def fit(self, features: FloatArray, target: FloatArray) -> PriorProbabilityEstimator:
        del features
        positives = float(np.sum(target))
        self.probability_ = (positives + self.smoothing) / (target.size + 2 * self.smoothing)
        return self

    def predict_proba(self, features: FloatArray) -> FloatArray:
        if self.probability_ is None:
            raise RuntimeError()
        positive = np.full(features.shape[0], self.probability_, dtype=float)
        return np.column_stack((1 - positive, positive))


class ShrunkMeanRegressor:
    def __init__(self, prior: float = 0.0, prior_weight: float = 5.0) -> None:
        self.prior = prior
        self.prior_weight = prior_weight
        self.mean_: float | None = None

    def fit(self, features: FloatArray, target: FloatArray) -> ShrunkMeanRegressor:
        del features
        self.mean_ = float(
            (np.sum(target) + self.prior * self.prior_weight) / (target.size + self.prior_weight)
        )
        return self

    def predict(self, features: FloatArray) -> FloatArray:
        if self.mean_ is None:
            raise RuntimeError()
        return np.full(features.shape[0], self.mean_, dtype=float)
