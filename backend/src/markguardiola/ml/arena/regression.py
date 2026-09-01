from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray
from scipy.special import gammaln

from markguardiola.ml.arena.candidates import CandidateFactory
from markguardiola.ml.arena.splits import TemporalFold, final_holdout_fold, rolling_origin_folds
from markguardiola.ml.evaluation import count_metrics, regression_metrics
from markguardiola.ml.evaluation.subgroups import subgroup_promotion_check
from markguardiola.ml.uncertainty import SplitConformalInterval

FloatArray = NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class RegressionCandidateReport:
    name: str
    family: str
    validation_metrics: dict[str, float]
    fold_metrics: tuple[dict[str, float], ...]
    failed: str | None = None


@dataclass(frozen=True, slots=True)
class RegressionChampion:
    candidate_name: str
    estimator: Any
    interval: SplitConformalInterval
    feature_names: tuple[str, ...]
    metrics: dict[str, float]
    subgroup_metrics: dict[str, dict[str, float]]
    holdout_season: str
    lower_bound: float
    upper_bound: float | None

    def predict(self, features: FloatArray) -> FloatArray:
        predictions = np.asarray(self.estimator.predict(features), dtype=float)
        predictions = np.maximum(predictions, self.lower_bound)
        if self.upper_bound is not None:
            predictions = np.minimum(predictions, self.upper_bound)
        return np.asarray(predictions, dtype=np.float64)


@dataclass(frozen=True, slots=True)
class RegressionArenaResult:
    champion: RegressionChampion
    reports: tuple[RegressionCandidateReport, ...]
    promoted_over_baseline: bool


class RegressionModelArena:
    def __init__(
        self,
        candidates: tuple[CandidateFactory, ...],
        *,
        count: bool = False,
        baseline_name: str = "shrunk_mean",
        lower_bound: float = 0.0,
        upper_bound: float | None = None,
        minimum_relative_improvement: float = 0.005,
        maximum_holdout_degradation: float = 0.05,
    ) -> None:
        if baseline_name not in {candidate.name for candidate in candidates}:
            raise ValueError()
        self._candidates = candidates
        self._count = count
        self._baseline_name = baseline_name
        self._lower_bound = lower_bound
        self._upper_bound = upper_bound
        self._minimum_relative_improvement = minimum_relative_improvement
        self._maximum_holdout_degradation = maximum_holdout_degradation

    def run(
        self,
        *,
        features: FloatArray,
        target: FloatArray,
        seasons: NDArray[np.str_],
        feature_names: tuple[str, ...],
        subgroups: NDArray[np.str_] | None = None,
    ) -> RegressionArenaResult:
        _validate_inputs(features, target, seasons, feature_names, self._lower_bound)
        folds = rolling_origin_folds(seasons)
        reports = tuple(
            self._evaluate(candidate, features, target, folds) for candidate in self._candidates
        )
        successful = [report for report in reports if report.failed is None]
        if not successful:
            raise RuntimeError()
        metric = "poisson_deviance" if self._count else "mae"
        baseline = next(report for report in successful if report.name == self._baseline_name)
        best_metric = min(report.validation_metrics[metric] for report in successful)
        tied = [
            report
            for report in successful
            if np.isclose(
                report.validation_metrics[metric],
                best_metric,
                rtol=1e-10,
                atol=1e-12,
            )
        ]

        complexity = {"baseline": 0, "linear": 1, "count": 2, "tree": 3}
        best = min(tied, key=lambda report: (complexity.get(report.family, 4), report.name))
        improvement = (
            baseline.validation_metrics[metric] - best.validation_metrics[metric]
        ) / baseline.validation_metrics[metric]
        promoted = best.name != baseline.name and improvement >= self._minimum_relative_improvement
        selected = best.name if promoted else baseline.name

        holdout = final_holdout_fold(seasons)
        selected_metrics, selected_predictions = self._fit_evaluate(
            self._factory(selected), features, target, holdout
        )
        baseline_metrics, baseline_predictions = self._fit_evaluate(
            self._factory(self._baseline_name), features, target, holdout
        )
        subgroup_metrics, subgroup_passed = subgroup_promotion_check(
            target[holdout.test_indices],
            selected_predictions,
            baseline_predictions,
            subgroups[holdout.test_indices] if subgroups is not None else None,
            kind="count" if self._count else "regression",
        )
        if selected != self._baseline_name and (
            not subgroup_passed
            or selected_metrics[metric]
            > baseline_metrics[metric] * (1 + self._maximum_holdout_degradation)
        ):
            promoted = False
            selected = self._baseline_name
            selected_metrics, selected_predictions = self._fit_evaluate(
                self._factory(selected), features, target, holdout
            )
            subgroup_metrics, _ = subgroup_promotion_check(
                target[holdout.test_indices],
                selected_predictions,
                baseline_predictions,
                subgroups[holdout.test_indices] if subgroups is not None else None,
                kind="count" if self._count else "regression",
            )

        residual_interval = SplitConformalInterval(
            coverage=0.8,
            lower_bound=self._lower_bound,
            upper_bound=self._upper_bound,
        ).fit(target[holdout.test_indices], selected_predictions)
        final_estimator, final_interval = self._fit_deployment(
            self._factory(selected), features, target, seasons
        )
        champion = RegressionChampion(
            candidate_name=selected,
            estimator=final_estimator,
            interval=final_interval,
            feature_names=feature_names,
            metrics={
                **selected_metrics,
                f"baseline_holdout_{metric}": baseline_metrics[metric],
                "challenger_subgroup_gate_passed": float(subgroup_passed),
            },
            subgroup_metrics=subgroup_metrics,
            holdout_season=holdout.test_season,
            lower_bound=self._lower_bound,
            upper_bound=self._upper_bound,
        )
        del residual_interval
        return RegressionArenaResult(champion, reports, promoted)

    def _evaluate(
        self,
        factory: CandidateFactory,
        features: FloatArray,
        target: FloatArray,
        folds: tuple[TemporalFold, ...],
    ) -> RegressionCandidateReport:
        metrics: list[dict[str, float]] = []
        try:
            for fold in folds:
                fold_metrics, _ = self._fit_evaluate(factory, features, target, fold)
                metrics.append(fold_metrics)
        except Exception:
            return RegressionCandidateReport(
                factory.name,
                factory.family,
                {},
                tuple(metrics),
                "candidate_failed",
            )
        aggregate = {key: float(np.mean([fold[key] for fold in metrics])) for key in metrics[0]}
        return RegressionCandidateReport(factory.name, factory.family, aggregate, tuple(metrics))

    def _fit_evaluate(
        self,
        factory: CandidateFactory,
        features: FloatArray,
        target: FloatArray,
        fold: TemporalFold,
    ) -> tuple[dict[str, float], FloatArray]:
        estimator = factory.build()
        train_indices = np.concatenate((fold.fit_indices, fold.calibration_indices))
        estimator.fit(features[train_indices], target[train_indices])
        predictions = self._bounded(estimator.predict(features[fold.test_indices]))
        metric_fn = count_metrics if self._count else regression_metrics
        metrics = metric_fn(target[fold.test_indices], predictions)
        if self._count:
            observed = target[fold.test_indices]
            mean = np.clip(predictions, 1e-7, None)
            metrics["poisson_negative_log_likelihood"] = float(
                np.mean(mean - observed * np.log(mean) + gammaln(observed + 1))
            )
            fitted = estimator.steps[-1][1] if hasattr(estimator, "steps") else estimator
            for attribute, name in (
                ("dispersion_", "training_dispersion"),
                ("hurdle_enabled_", "training_hurdle_enabled"),
                ("excess_zero_fraction_", "training_excess_zero_fraction"),
            ):
                if hasattr(fitted, attribute):
                    metrics[name] = float(getattr(fitted, attribute))
        return metrics, predictions

    def _fit_deployment(
        self,
        factory: CandidateFactory,
        features: FloatArray,
        target: FloatArray,
        seasons: NDArray[np.str_],
    ) -> tuple[Any, SplitConformalInterval]:
        values = np.asarray(seasons, dtype=str)
        calibration_season = sorted(np.unique(values))[-1]
        fit_indices = np.flatnonzero(values < calibration_season)
        calibration_indices = np.flatnonzero(values == calibration_season)
        estimator = factory.build()
        estimator.fit(features[fit_indices], target[fit_indices])
        calibration_predictions = self._bounded(estimator.predict(features[calibration_indices]))
        interval = SplitConformalInterval(
            coverage=0.8,
            lower_bound=self._lower_bound,
            upper_bound=self._upper_bound,
        ).fit(target[calibration_indices], calibration_predictions)
        return estimator, interval

    def _bounded(self, predictions: object) -> FloatArray:
        values = np.maximum(np.asarray(predictions, dtype=float), self._lower_bound)
        bounded = np.minimum(values, self._upper_bound) if self._upper_bound is not None else values
        return np.asarray(bounded, dtype=np.float64)

    def _factory(self, name: str) -> CandidateFactory:
        return next(candidate for candidate in self._candidates if candidate.name == name)


def _validate_inputs(
    features: FloatArray,
    target: FloatArray,
    seasons: NDArray[np.str_],
    feature_names: tuple[str, ...],
    lower_bound: float,
) -> None:
    if features.ndim != 2 or target.ndim != 1:
        raise ValueError()
    if features.shape[0] != target.size or target.size != seasons.size:
        raise ValueError()
    if features.shape[1] != len(feature_names):
        raise ValueError()
    if np.any(target < lower_bound):
        raise ValueError()
