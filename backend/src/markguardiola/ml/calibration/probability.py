from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss

FloatArray = NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class CalibrationSelection:
    method: str
    validation_log_loss: float


class ProbabilityCalibrator:
    def __init__(self, method: str, model: Any = None) -> None:
        self.method = method
        self.model = model

    @classmethod
    def select(
        cls, raw_probabilities: FloatArray, y_validation: FloatArray
    ) -> tuple[ProbabilityCalibrator, CalibrationSelection]:
        probabilities = np.clip(np.asarray(raw_probabilities, dtype=float), 1e-7, 1 - 1e-7)
        target = np.asarray(y_validation, dtype=float)
        candidates: list[ProbabilityCalibrator] = [cls("identity")]
        if np.unique(target).size > 1:
            logits = np.log(probabilities / (1 - probabilities)).reshape(-1, 1)
            platt = LogisticRegression(C=1e6, solver="lbfgs", random_state=0)
            platt.fit(logits, target)
            candidates.append(cls("platt", platt))

            if target.size >= 500:
                isotonic = IsotonicRegression(out_of_bounds="clip")
                isotonic.fit(probabilities, target)
                candidates.append(cls("isotonic", isotonic))
        scored = [
            (
                float(log_loss(target, candidate.predict(probabilities), labels=[0.0, 1.0])),
                candidate,
            )
            for candidate in candidates
        ]
        score, winner = min(scored, key=lambda item: (item[0], _method_rank(item[1].method)))
        return winner, CalibrationSelection(winner.method, score)

    def predict(self, raw_probabilities: FloatArray) -> FloatArray:
        probabilities = np.clip(np.asarray(raw_probabilities, dtype=float), 1e-7, 1 - 1e-7)
        if self.method == "identity":
            return np.asarray(probabilities, dtype=np.float64)
        if self.method == "platt":
            logits = np.log(probabilities / (1 - probabilities)).reshape(-1, 1)
            calibrated = np.asarray(self.model.predict_proba(logits)[:, 1], dtype=float)
            return np.asarray(np.clip(calibrated, 1e-7, 1 - 1e-7), dtype=np.float64)
        if self.method == "isotonic":
            calibrated = np.asarray(self.model.predict(probabilities), dtype=float)
            return np.asarray(np.clip(calibrated, 1e-7, 1 - 1e-7), dtype=np.float64)
        raise ValueError()


def _method_rank(method: str) -> int:
    return {"identity": 0, "platt": 1, "isotonic": 2}.get(method, 99)
