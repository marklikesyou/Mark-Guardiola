from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from markguardiola.ml.arena.candidates import CandidateFactory
from markguardiola.ml.arena.splits import TemporalFold, final_holdout_fold, rolling_origin_folds
from markguardiola.ml.calibration import ProbabilityCalibrator
from markguardiola.ml.evaluation.metrics import probability_metrics
from markguardiola.ml.evaluation.subgroups import subgroup_promotion_check

FloatArray = NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class CandidateReport:
    name: str
    family: str
    validation_metrics: dict[str, float]
    fold_metrics: tuple[dict[str, float], ...]
    calibration_methods: tuple[str, ...]
    failed: str | None = None


@dataclass(frozen=True, slots=True)
class ProbabilityChampion:
    candidate_name: str
    estimator: Any
    calibrator: ProbabilityCalibrator
    feature_names: tuple[str, ...]
    metrics: dict[str, float]
    subgroup_metrics: dict[str, dict[str, float]]
    holdout_season: str

    def predict_proba(self, features: FloatArray) -> FloatArray:
        raw = np.asarray(self.estimator.predict_proba(features)[:, 1], dtype=float)
        return self.calibrator.predict(raw)


@dataclass(frozen=True, slots=True)
class ProbabilityArenaResult:
    champion: ProbabilityChampion
    reports: tuple[CandidateReport, ...]
    promoted_over_baseline: bool


class ProbabilityModelArena:
    def __init__(
        self,
        candidates: tuple[CandidateFactory, ...],
        *,
        baseline_name: str = "prior",
        minimum_relative_improvement: float = 0.005,
        maximum_calibration_degradation: float = 0.02,
        maximum_holdout_degradation: float = 0.05,
    ) -> None:
        names = [candidate.name for candidate in candidates]
        if baseline_name not in names:
            raise ValueError()
        if len(names) != len(set(names)):
            raise ValueError()
        self._candidates = candidates
        self._baseline_name = baseline_name
        self._minimum_relative_improvement = minimum_relative_improvement
        self._maximum_calibration_degradation = maximum_calibration_degradation
        self._maximum_holdout_degradation = maximum_holdout_degradation

    def run(
        self,
        *,
        features: FloatArray,
        target: FloatArray,
        seasons: NDArray[np.str_],
        feature_names: tuple[str, ...],
        subgroups: NDArray[np.str_] | None = None,
    ) -> ProbabilityArenaResult:
        _validate_inputs(features, target, seasons, feature_names)
        folds = rolling_origin_folds(seasons)
        reports = tuple(
            self._evaluate_candidate(factory, features, target, folds)
            for factory in self._candidates
        )
        successful = [report for report in reports if report.failed is None]
        if not successful:
            raise RuntimeError()
        baseline = next(report for report in successful if report.name == self._baseline_name)
        best = min(
            successful, key=lambda report: (report.validation_metrics["log_loss"], report.name)
        )
        relative_improvement = (
            baseline.validation_metrics["log_loss"] - best.validation_metrics["log_loss"]
        ) / baseline.validation_metrics["log_loss"]
        calibrated_enough = (
            best.validation_metrics["calibration_error"]
            <= baseline.validation_metrics["calibration_error"]
            + self._maximum_calibration_degradation
        )
        promoted = (
            best.name != baseline.name
            and relative_improvement >= self._minimum_relative_improvement
            and calibrated_enough
        )
        selected_name = best.name if promoted else baseline.name

        holdout = final_holdout_fold(seasons)
        selected_factory = self._factory(selected_name)
        baseline_factory = self._factory(self._baseline_name)
        _selected_model, _selected_calibrator, selected_metrics, selected_predictions = (
            _fit_evaluate(selected_factory, features, target, holdout)
        )
        _, _, baseline_holdout_metrics, baseline_predictions = _fit_evaluate(
            baseline_factory, features, target, holdout
        )
        subgroup_metrics, subgroup_passed = subgroup_promotion_check(
            target[holdout.test_indices],
            selected_predictions,
            baseline_predictions,
            subgroups[holdout.test_indices] if subgroups is not None else None,
            kind="probability",
        )
        if selected_name != self._baseline_name and (
            not subgroup_passed
            or selected_metrics["log_loss"]
            > baseline_holdout_metrics["log_loss"] * (1 + self._maximum_holdout_degradation)
        ):
            promoted = False
            selected_name = self._baseline_name
            _selected_model, _selected_calibrator, selected_metrics, selected_predictions = (
                _fit_evaluate(baseline_factory, features, target, holdout)
            )
            subgroup_metrics, _ = subgroup_promotion_check(
                target[holdout.test_indices],
                selected_predictions,
                baseline_predictions,
                subgroups[holdout.test_indices] if subgroups is not None else None,
                kind="probability",
            )
        final_model, final_calibrator = _fit_deployment_model(
            self._factory(selected_name), features, target, seasons
        )
        champion = ProbabilityChampion(
            candidate_name=selected_name,
            estimator=final_model,
            calibrator=final_calibrator,
            feature_names=feature_names,
            metrics={
                **selected_metrics,
                "baseline_holdout_log_loss": baseline_holdout_metrics["log_loss"],
                "challenger_subgroup_gate_passed": float(subgroup_passed),
            },
            subgroup_metrics=subgroup_metrics,
            holdout_season=holdout.test_season,
        )
        return ProbabilityArenaResult(champion, reports, promoted)

    def _evaluate_candidate(
        self,
        factory: CandidateFactory,
        features: FloatArray,
        target: FloatArray,
        folds: tuple[TemporalFold, ...],
    ) -> CandidateReport:
        metrics: list[dict[str, float]] = []
        methods: list[str] = []
        try:
            for fold in folds:
                _, calibrator, fold_metrics, _ = _fit_evaluate(factory, features, target, fold)
                metrics.append(fold_metrics)
                methods.append(calibrator.method)
        except Exception:
            return CandidateReport(
                name=factory.name,
                family=factory.family,
                validation_metrics={},
                fold_metrics=tuple(metrics),
                calibration_methods=tuple(methods),
                failed="candidate_failed",
            )
        aggregate = {key: float(np.mean([fold[key] for fold in metrics])) for key in metrics[0]}
        return CandidateReport(
            name=factory.name,
            family=factory.family,
            validation_metrics=aggregate,
            fold_metrics=tuple(metrics),
            calibration_methods=tuple(methods),
        )

    def _factory(self, name: str) -> CandidateFactory:
        return next(candidate for candidate in self._candidates if candidate.name == name)


def _fit_evaluate(
    factory: CandidateFactory,
    features: FloatArray,
    target: FloatArray,
    fold: TemporalFold,
) -> tuple[Any, ProbabilityCalibrator, dict[str, float], FloatArray]:
    estimator = factory.build()
    estimator.fit(features[fold.fit_indices], target[fold.fit_indices])
    raw_calibration = np.asarray(
        estimator.predict_proba(features[fold.calibration_indices])[:, 1], dtype=float
    )
    calibrator, _ = ProbabilityCalibrator.select(raw_calibration, target[fold.calibration_indices])
    raw_test = np.asarray(estimator.predict_proba(features[fold.test_indices])[:, 1], dtype=float)
    predictions = calibrator.predict(raw_test)
    return (
        estimator,
        calibrator,
        probability_metrics(target[fold.test_indices], predictions),
        predictions,
    )


def _fit_deployment_model(
    factory: CandidateFactory,
    features: FloatArray,
    target: FloatArray,
    seasons: NDArray[np.str_],
) -> tuple[Any, ProbabilityCalibrator]:
    values = np.asarray(seasons, dtype=str)
    calibration_season = sorted(np.unique(values))[-1]
    fit_indices = np.flatnonzero(values < calibration_season)
    calibration_indices = np.flatnonzero(values == calibration_season)
    estimator = factory.build()
    estimator.fit(features[fit_indices], target[fit_indices])
    raw = np.asarray(estimator.predict_proba(features[calibration_indices])[:, 1], dtype=float)
    calibrator, _ = ProbabilityCalibrator.select(raw, target[calibration_indices])
    return estimator, calibrator


def _validate_inputs(
    features: FloatArray,
    target: FloatArray,
    seasons: NDArray[np.str_],
    feature_names: tuple[str, ...],
) -> None:
    if features.ndim != 2 or target.ndim != 1:
        raise ValueError()
    if features.shape[0] != target.size or target.size != seasons.size:
        raise ValueError()
    if features.shape[1] != len(feature_names):
        raise ValueError()
    if not set(np.unique(target)).issubset({0.0, 1.0}):
        raise ValueError()
