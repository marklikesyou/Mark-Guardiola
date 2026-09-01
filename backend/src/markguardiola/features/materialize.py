from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from markguardiola.features.point_in_time import assert_no_future_information


@dataclass(frozen=True, slots=True)
class MaterializedSnapshot:
    storage_path: Path
    manifest_path: Path
    content_sha256: str
    row_count: int


def materialize_snapshot(
    frame: pl.DataFrame,
    *,
    output_root: Path,
    feature_schema_version: str,
    source_manifest: dict[str, object],
) -> MaterializedSnapshot:
    assert_no_future_information(frame)
    output_root.mkdir(parents=True, exist_ok=True)
    temporary = output_root / f".snapshot-{os.getpid()}.parquet"
    frame.write_parquet(temporary, compression="zstd", statistics=True)
    digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
    directory = output_root / feature_schema_version
    directory.mkdir(parents=True, exist_ok=True)
    storage_path = directory / f"{digest}.parquet"
    if storage_path.exists():
        temporary.unlink()
    else:
        temporary.replace(storage_path)
    manifest_path = storage_path.with_suffix(".manifest.json")
    if not manifest_path.exists():
        cutoffs = frame["prediction_cutoff"]
        payload = {
            "feature_schema_version": feature_schema_version,
            "content_sha256": digest,
            "row_count": frame.height,
            "columns": frame.columns,
            "prediction_cutoff_min": str(cutoffs.min()),
            "prediction_cutoff_max": str(cutoffs.max()),
            "source_manifest": source_manifest,
            "materialized_at": datetime.now(UTC).isoformat(),
        }
        manifest_path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")
    return MaterializedSnapshot(storage_path, manifest_path, digest, frame.height)
