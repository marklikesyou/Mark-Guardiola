from __future__ import annotations

from dataclasses import dataclass

import polars as pl


@dataclass(frozen=True, slots=True)
class LeakageViolation:
    snapshot_row_id: str
    prediction_cutoff: object
    source_column: str
    source_available_at: object


class PointInTimeLeakageError(RuntimeError):
    def __init__(self, violations: list[LeakageViolation]) -> None:
        self.violations = violations
        super().__init__()


def assert_no_future_information(
    frame: pl.DataFrame,
    *,
    cutoff_column: str = "prediction_cutoff",
    lineage_columns: tuple[str, ...] | None = None,
) -> None:
    required = {"snapshot_row_id", cutoff_column}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError()
    lineages = lineage_columns or tuple(
        column for column in frame.columns if column.endswith("_max_available_at")
    )
    violations: list[LeakageViolation] = []
    for source_column in lineages:
        if source_column not in frame.columns:
            raise ValueError()
        bad_rows = frame.filter(
            pl.col(source_column).is_not_null()
            & (pl.col(source_column).cast(pl.Int64) > pl.col(cutoff_column).cast(pl.Int64))
        ).select("snapshot_row_id", cutoff_column, source_column)
        for row in bad_rows.iter_rows(named=True):
            violations.append(
                LeakageViolation(
                    snapshot_row_id=str(row["snapshot_row_id"]),
                    prediction_cutoff=row[cutoff_column],
                    source_column=source_column,
                    source_available_at=row[source_column],
                )
            )
    if violations:
        raise PointInTimeLeakageError(violations)
