from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import minimize
from scipy.special import digamma, expit, gammaln
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.linear_model import LogisticRegression, PoissonRegressor

FloatArray = NDArray[np.float64]


def negative_binomial_loss(
    parameters: FloatArray,
    design: FloatArray,
    target: FloatArray,
    penalty: float,
) -> tuple[float, FloatArray]:
    coefficients, log_dispersion = parameters[:-1], parameters[-1]
    log_mean = design @ coefficients
    size = np.exp(-log_dispersion)
    log_size = -log_dispersion
    log_total = np.logaddexp(log_size, log_mean)
    log_probability = (
        gammaln(target + size)
        - gammaln(size)
        - gammaln(target + 1)
        + size * (log_size - log_total)
        + target * (log_mean - log_total)
    )
    coefficient_gradient = (
        design.T @ ((size + target) * expit(log_mean - log_size) - target) / target.size
    )
    coefficient_gradient[1:] += penalty * coefficients[1:]
    dispersion_gradient = size * np.mean(
        digamma(target + size)
        - digamma(size)
        + log_size
        + 1
        - log_total
        - (1 + target / size) * expit(log_size - log_mean)
    )
    loss = -float(log_probability.mean()) + 0.5 * penalty * float(
        coefficients[1:] @ coefficients[1:]
    )
    return loss, np.append(coefficient_gradient, dispersion_gradient)


class NegativeBinomialRegressor(RegressorMixin, BaseEstimator):
    def __init__(self, penalty: float = 1.0, max_iter: int = 1000) -> None:
        self.penalty = penalty
        self.max_iter = max_iter

    def fit(self, features: FloatArray, target: FloatArray) -> NegativeBinomialRegressor:
        features, target = _validate(features, target)
        self.n_features_in_ = features.shape[1]
        self.zero_target_ = not np.any(target)
        if self.zero_target_:
            self.coef_ = np.zeros(features.shape[1])
            self.intercept_, self.dispersion_ = 0.0, 0.0
            return self
        initial = PoissonRegressor(alpha=self.penalty, max_iter=self.max_iter).fit(features, target)
        means = initial.predict(features)
        dispersion = max(0.01, float(np.mean((target - means) ** 2 - means) / np.mean(means**2)))
        design = np.column_stack((np.ones(target.size), features))
        result = minimize(
            negative_binomial_loss,
            np.r_[initial.intercept_, initial.coef_, np.log(dispersion)],
            args=(design, target, self.penalty),
            jac=True,
            method="L-BFGS-B",
            bounds=[(None, None)] * design.shape[1] + [(-10, 5)],
            options={"maxiter": self.max_iter, "ftol": 1e-9},
        )
        if not result.success or not np.all(np.isfinite(result.x)):
            raise RuntimeError()
        self.intercept_ = float(result.x[0])
        self.coef_ = result.x[1:-1]
        self.dispersion_ = float(np.exp(result.x[-1]))
        return self

    def predict(self, features: FloatArray) -> FloatArray:
        if self.zero_target_:
            return np.zeros(features.shape[0], dtype=float)
        return np.asarray(
            np.exp(np.clip(features @ self.coef_ + self.intercept_, -20, 20)), dtype=float
        )


class DiagnosticHurdleRegressor(RegressorMixin, BaseEstimator):
    def __init__(self, penalty: float = 1.0, minimum_excess_zero: float = 0.02) -> None:
        self.penalty = penalty
        self.minimum_excess_zero = minimum_excess_zero

    def fit(self, features: FloatArray, target: FloatArray) -> DiagnosticHurdleRegressor:
        features, target = _validate(features, target)
        self.n_features_in_ = features.shape[1]
        self.zero_target_ = not np.any(target)
        self.hurdle_enabled_ = False
        self.excess_zero_fraction_ = 0.0
        if self.zero_target_:
            return self
        self.poisson_ = PoissonRegressor(alpha=self.penalty, max_iter=1000).fit(features, target)
        self.excess_zero_fraction_ = float(
            np.mean(target == 0) - np.mean(np.exp(-self.poisson_.predict(features)))
        )
        self.hurdle_enabled_ = (
            self.excess_zero_fraction_ > self.minimum_excess_zero
            and np.unique(target > 0).size == 2
        )
        if not self.hurdle_enabled_:
            return self
        self.event_ = LogisticRegression(C=1 / max(self.penalty, 1e-8), max_iter=1000).fit(
            features, target > 0
        )

        positive = target > 0
        self.constant_positive_ = bool(np.all(target[positive] == 1))
        if not self.constant_positive_:
            self.positive_ = PoissonRegressor(alpha=self.penalty, max_iter=1000).fit(
                features[positive], target[positive] - 1
            )
        return self

    def predict(self, features: FloatArray) -> FloatArray:
        if self.zero_target_:
            return np.zeros(features.shape[0], dtype=float)
        if not self.hurdle_enabled_:
            return np.asarray(self.poisson_.predict(features), dtype=float)
        conditional = (
            np.ones(features.shape[0])
            if self.constant_positive_
            else 1 + self.positive_.predict(features)
        )
        return np.asarray(self.event_.predict_proba(features)[:, 1] * conditional, dtype=float)


def _validate(features: FloatArray, target: FloatArray) -> tuple[FloatArray, FloatArray]:
    features, target = np.asarray(features, dtype=float), np.asarray(target, dtype=float)
    if (
        features.ndim != 2
        or target.ndim != 1
        or target.size != features.shape[0]
        or target.size == 0
        or not np.all(np.isfinite(features))
        or not np.all(np.isfinite(target))
        or np.any(target < 0)
        or not np.all(target == np.floor(target))
    ):
        raise ValueError()
    return features, target
