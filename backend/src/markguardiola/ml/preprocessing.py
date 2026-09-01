from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.utils.validation import check_is_fitted


class AllMissingColumnGuard(TransformerMixin, BaseEstimator):
    def fit(
        self, X: NDArray[np.float64], y: NDArray[np.float64] | None = None
    ) -> AllMissingColumnGuard:
        values = np.asarray(X, dtype=float)
        self.n_features_in_ = values.shape[1]
        self.empty_columns_ = np.isnan(values).all(axis=0)
        return self

    def transform(self, X: NDArray[np.float64]) -> NDArray[np.float64]:
        check_is_fitted(self, "empty_columns_")
        values = np.asarray(X, dtype=float).copy()
        if values.shape[1] != self.n_features_in_:
            raise ValueError()
        values[:, self.empty_columns_] = np.nan_to_num(values[:, self.empty_columns_], nan=0.0)
        return values
