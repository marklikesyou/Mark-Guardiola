from __future__ import annotations

import importlib.util
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from sklearn.ensemble import (
    ExtraTreesClassifier,
    HistGradientBoostingClassifier,
    HistGradientBoostingRegressor,
)
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, PoissonRegressor, Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from markguardiola.ml.baselines import PriorProbabilityEstimator, ShrunkMeanRegressor
from markguardiola.ml.baselines.counts import DiagnosticHurdleRegressor, NegativeBinomialRegressor
from markguardiola.ml.preprocessing import AllMissingColumnGuard


@dataclass(frozen=True, slots=True)
class CandidateFactory:
    name: str
    build: Callable[[], Any]
    family: str
    optional_dependency: str | None = None


@lru_cache(maxsize=1)
def require_external_ml_runtime() -> None:

    for name in ("lightgbm", "xgboost", "catboost"):
        try:
            importlib.import_module(name)
        except Exception:
            raise RuntimeError() from None


def probability_candidates(
    *, random_seed: int = 2026, include_external: bool = True
) -> tuple[CandidateFactory, ...]:
    candidates: list[CandidateFactory] = [
        CandidateFactory("prior", lambda: PriorProbabilityEstimator(), "baseline"),
        CandidateFactory(
            "logistic_regression",
            lambda: make_pipeline(
                SimpleImputer(strategy="median", add_indicator=True),
                StandardScaler(),
                LogisticRegression(C=1.0, max_iter=2000, random_state=random_seed),
            ),
            "linear",
        ),
        CandidateFactory(
            "hist_gradient_boosting",
            lambda: make_pipeline(
                AllMissingColumnGuard(),
                HistGradientBoostingClassifier(
                    learning_rate=0.05,
                    max_iter=300,
                    max_leaf_nodes=31,
                    l2_regularization=1.0,
                    random_state=random_seed,
                ),
            ),
            "tree",
        ),
        CandidateFactory(
            "extra_trees",
            lambda: make_pipeline(
                SimpleImputer(strategy="median", add_indicator=True),
                ExtraTreesClassifier(
                    n_estimators=400,
                    min_samples_leaf=8,
                    class_weight="balanced",
                    n_jobs=1,
                    random_state=random_seed,
                ),
            ),
            "tree",
        ),
    ]
    if include_external:
        candidates.extend(_external_probability_candidates(random_seed))
    return tuple(candidates)


def regression_candidates(
    *, random_seed: int = 2026, count: bool = False, include_external: bool = True
) -> tuple[CandidateFactory, ...]:
    def linear_factory() -> Any:
        if count:
            return make_pipeline(
                SimpleImputer(strategy="median", add_indicator=True),
                StandardScaler(),
                PoissonRegressor(alpha=1.0, max_iter=1000),
            )
        return make_pipeline(
            SimpleImputer(strategy="median", add_indicator=True),
            StandardScaler(),
            Ridge(alpha=1.0, random_state=random_seed),
        )

    candidates: list[CandidateFactory] = [
        CandidateFactory("shrunk_mean", lambda: ShrunkMeanRegressor(), "baseline"),
        CandidateFactory(
            "poisson_regression" if count else "ridge",
            linear_factory,
            "linear",
        ),
        CandidateFactory(
            "hist_gradient_boosting_poisson" if count else "hist_gradient_boosting",
            lambda: make_pipeline(
                AllMissingColumnGuard(),
                HistGradientBoostingRegressor(
                    loss="poisson" if count else "squared_error",
                    learning_rate=0.05,
                    max_iter=300,
                    max_leaf_nodes=31,
                    l2_regularization=1.0,
                    random_state=random_seed,
                ),
            ),
            "tree",
        ),
    ]
    if count:
        candidates.extend(
            [
                CandidateFactory(
                    "negative_binomial",
                    lambda: make_pipeline(
                        SimpleImputer(strategy="median", add_indicator=True),
                        StandardScaler(),
                        NegativeBinomialRegressor(),
                    ),
                    "count",
                ),
                CandidateFactory(
                    "diagnostic_hurdle",
                    lambda: make_pipeline(
                        SimpleImputer(strategy="median", add_indicator=True),
                        StandardScaler(),
                        DiagnosticHurdleRegressor(),
                    ),
                    "count",
                ),
            ]
        )
    if include_external:
        candidates.extend(_external_regression_candidates(random_seed, count))
    return tuple(candidates)


def _external_probability_candidates(random_seed: int) -> list[CandidateFactory]:
    candidates: list[CandidateFactory] = []
    if importlib.util.find_spec("lightgbm") is not None:
        candidates.append(
            CandidateFactory(
                "lightgbm",
                lambda: _lightgbm_classifier(random_seed),
                "tree",
                "lightgbm",
            )
        )
    if importlib.util.find_spec("xgboost") is not None:
        candidates.append(
            CandidateFactory(
                "xgboost",
                lambda: _xgboost_classifier(random_seed),
                "tree",
                "xgboost",
            )
        )
    if importlib.util.find_spec("catboost") is not None:
        candidates.append(
            CandidateFactory(
                "catboost",
                lambda: _catboost_classifier(random_seed),
                "tree",
                "catboost",
            )
        )
    return candidates


def _external_regression_candidates(random_seed: int, count: bool) -> list[CandidateFactory]:
    candidates: list[CandidateFactory] = []
    if importlib.util.find_spec("lightgbm") is not None:
        candidates.append(
            CandidateFactory(
                "lightgbm",
                lambda: _lightgbm_regressor(random_seed, count),
                "tree",
                "lightgbm",
            )
        )
    if importlib.util.find_spec("xgboost") is not None:
        candidates.append(
            CandidateFactory(
                "xgboost",
                lambda: _xgboost_regressor(random_seed, count),
                "tree",
                "xgboost",
            )
        )
    if importlib.util.find_spec("catboost") is not None:
        candidates.append(
            CandidateFactory(
                "catboost",
                lambda: _catboost_regressor(random_seed, count),
                "tree",
                "catboost",
            )
        )
    return candidates


def _lightgbm_classifier(seed: int) -> Any:
    from lightgbm import LGBMClassifier

    return LGBMClassifier(
        n_estimators=500,
        learning_rate=0.03,
        num_leaves=31,
        min_child_samples=30,
        reg_lambda=1.0,
        random_state=seed,
        verbosity=-1,
    )


def _xgboost_classifier(seed: int) -> Any:
    from xgboost import XGBClassifier

    return XGBClassifier(
        n_estimators=500,
        learning_rate=0.03,
        max_depth=5,
        min_child_weight=5,
        subsample=0.9,
        colsample_bytree=0.9,
        reg_lambda=1.0,
        eval_metric="logloss",
        random_state=seed,
    )


def _catboost_classifier(seed: int) -> Any:
    from catboost import CatBoostClassifier

    return CatBoostClassifier(
        iterations=500,
        learning_rate=0.03,
        depth=6,
        l2_leaf_reg=3.0,
        random_seed=seed,
        verbose=False,
        allow_writing_files=False,
    )


def _lightgbm_regressor(seed: int, count: bool) -> Any:
    from lightgbm import LGBMRegressor

    return LGBMRegressor(
        objective="poisson" if count else "regression_l1",
        n_estimators=500,
        learning_rate=0.03,
        num_leaves=31,
        min_child_samples=30,
        reg_lambda=1.0,
        random_state=seed,
        verbosity=-1,
    )


def _xgboost_regressor(seed: int, count: bool) -> Any:
    from xgboost import XGBRegressor

    return XGBRegressor(
        objective="count:poisson" if count else "reg:absoluteerror",
        n_estimators=500,
        learning_rate=0.03,
        max_depth=5,
        min_child_weight=5,
        subsample=0.9,
        colsample_bytree=0.9,
        reg_lambda=1.0,
        random_state=seed,
    )


def _catboost_regressor(seed: int, count: bool) -> Any:
    from catboost import CatBoostRegressor

    return CatBoostRegressor(
        loss_function="Poisson" if count else "MAE",
        iterations=500,
        learning_rate=0.03,
        depth=6,
        l2_leaf_reg=3.0,
        random_seed=seed,
        verbose=False,
        allow_writing_files=False,
    )
