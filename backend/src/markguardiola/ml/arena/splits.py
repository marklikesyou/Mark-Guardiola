from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True, slots=True)
class TemporalFold:
    fit_indices: NDArray[np.int64]
    calibration_indices: NDArray[np.int64]
    test_indices: NDArray[np.int64]
    calibration_season: str
    test_season: str


def rolling_origin_folds(
    seasons: NDArray[np.str_],
    *,
    exclude_final_holdout: bool = True,
) -> tuple[TemporalFold, ...]:
    values = np.asarray(seasons, dtype=str)
    unique = sorted(np.unique(values))
    if len(unique) < 4:
        raise ValueError()
    test_seasons = unique[2:-1] if exclude_final_holdout else unique[2:]
    folds: list[TemporalFold] = []
    for test_season in test_seasons:
        prior = [season for season in unique if season < test_season]
        calibration_season = prior[-1]
        fit_seasons = prior[:-1]
        folds.append(
            TemporalFold(
                fit_indices=np.flatnonzero(np.isin(values, fit_seasons)).astype(np.int64),
                calibration_indices=np.flatnonzero(values == calibration_season).astype(np.int64),
                test_indices=np.flatnonzero(values == test_season).astype(np.int64),
                calibration_season=calibration_season,
                test_season=test_season,
            )
        )
    if not folds:
        raise ValueError()
    return tuple(folds)


def final_holdout_fold(seasons: NDArray[np.str_]) -> TemporalFold:
    values = np.asarray(seasons, dtype=str)
    unique = sorted(np.unique(values))
    if len(unique) < 3:
        raise ValueError()
    test = unique[-1]
    calibration = unique[-2]
    fit = unique[:-2]
    return TemporalFold(
        fit_indices=np.flatnonzero(np.isin(values, fit)).astype(np.int64),
        calibration_indices=np.flatnonzero(values == calibration).astype(np.int64),
        test_indices=np.flatnonzero(values == test).astype(np.int64),
        calibration_season=calibration,
        test_season=test,
    )
