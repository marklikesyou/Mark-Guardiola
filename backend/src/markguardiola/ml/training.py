from __future__ import annotations

import platform
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from importlib.metadata import version as package_version
from pathlib import Path
from typing import cast

import numpy as np
import polars as pl
from sqlalchemy import select, update

from markguardiola.core.config import get_settings
from markguardiola.db.models import FeatureSnapshotMetadata, ModelVersion
from markguardiola.db.session import get_session_factory
from markguardiola.ml.arena import (
    ProbabilityModelArena,
    RegressionModelArena,
    probability_candidates,
    regression_candidates,
)
from markguardiola.ml.arena.candidates import require_external_ml_runtime
from markguardiola.ml.registry import LocalModelRegistry, ModelManifest, manifest_version
from markguardiola.ml.registry.artifacts import archive_source_code, write_evaluation
from markguardiola.ml.targets import ProblemKind, target_definition


async def train_from_snapshot(parameters: dict[str, object]) -> dict[str, object]:
    snapshot_id = _required_uuid(parameters, "feature_snapshot_id")
    target_name = _required_string(parameters, "target")
    label_column = _string(parameters.get("label_column"), target_name)
    season_column = _string(parameters.get("season_column"), "season")
    include_external = bool(parameters.get("include_external", True))
    random_seed = _integer(parameters.get("random_seed"), 2026, "random_seed")
    definition = target_definition(target_name)
    if include_external:
        require_external_ml_runtime()
    code_revision = _string(parameters.get("code_revision"), "") or archive_source_code(
        get_settings().artifact_root
    )
    if not (get_settings().artifact_root / "source" / f"{code_revision}.zip").is_file():
        raise ValueError()

    async with get_session_factory()() as session:
        snapshot = await session.get(FeatureSnapshotMetadata, snapshot_id)
        if snapshot is None:
            raise ValueError()
        snapshot_path = _validated_snapshot_path(snapshot.storage_path)
        feature_names = _feature_names(parameters, snapshot.feature_names)
        frame = pl.read_parquet(snapshot_path)
        required = {*feature_names, label_column, season_column}
        missing = required.difference(frame.columns)
        if missing:
            raise ValueError()
        clean = prepare_target_frame(frame, target_name, label_column, season_column)
        if target_name in {"team_goals", "team_goals_conceded", "clean_sheet_probability"}:
            clean = clean.unique(subset=["team_id", "match_id"], maintain_order=True)
        if clean.height < 100:
            raise ValueError()
        features = clean.select(feature_names).cast(pl.Float64, strict=False).to_numpy()
        labels = clean[label_column].cast(pl.Float64).to_numpy()
        seasons = clean[season_column].cast(pl.String).to_numpy()
        unique_seasons = np.unique(seasons)
        if unique_seasons.size < 4:
            raise ValueError()

        subgroup_column = parameters.get("subgroup_column")
        subgroups = (
            clean[_string(subgroup_column, "")].cast(pl.String).to_numpy()
            if subgroup_column
            and target_name not in {"team_goals", "team_goals_conceded", "clean_sheet_probability"}
            else None
        )
        if definition.kind == ProblemKind.PROBABILITY:
            result = ProbabilityModelArena(
                probability_candidates(
                    random_seed=random_seed,
                    include_external=include_external,
                )
            ).run(
                features=np.asarray(features, dtype=np.float64),
                target=np.asarray(labels, dtype=np.float64),
                seasons=np.asarray(seasons, dtype=np.str_),
                feature_names=feature_names,
                subgroups=(np.asarray(subgroups, dtype=np.str_) if subgroups is not None else None),
            )
            probability_champion = result.champion
            champion_model: object = probability_champion
            algorithm = probability_champion.candidate_name
            metrics = probability_champion.metrics
            subgroup_metrics = probability_champion.subgroup_metrics
            calibration: dict[str, object] = {"method": probability_champion.calibrator.method}
            promoted = result.promoted_over_baseline
            reports = [asdict(report) for report in result.reports]
            holdout_season = probability_champion.holdout_season
        else:
            result_regression = RegressionModelArena(
                regression_candidates(
                    random_seed=random_seed,
                    count=definition.kind == ProblemKind.COUNT,
                    include_external=include_external,
                ),
                count=definition.kind == ProblemKind.COUNT,
                lower_bound=definition.lower_bound,
                upper_bound=definition.upper_bound,
            ).run(
                features=np.asarray(features, dtype=np.float64),
                target=np.asarray(labels, dtype=np.float64),
                seasons=np.asarray(seasons, dtype=np.str_),
                feature_names=feature_names,
                subgroups=(np.asarray(subgroups, dtype=np.str_) if subgroups is not None else None),
            )
            regression_champion = result_regression.champion
            champion_model = regression_champion
            algorithm = regression_champion.candidate_name
            metrics = regression_champion.metrics
            subgroup_metrics = regression_champion.subgroup_metrics
            calibration = {
                "method": "split_conformal",
                "coverage": regression_champion.interval.coverage,
            }
            promoted = result_regression.promoted_over_baseline
            reports = [asdict(report) for report in result_regression.reports]
            holdout_season = regression_champion.holdout_season

        model_parameters: dict[str, object] = {
            "random_seed": random_seed,
            "include_external": include_external,
            "feature_names": list(feature_names),
            "code_revision_kind": "source_sha256",
            "python_version": platform.python_version(),
            "dependency_versions": {
                name: package_version(name)
                for name in (
                    "numpy",
                    "scikit-learn",
                    "polars",
                    "scipy",
                    *(("lightgbm", "xgboost", "catboost") if include_external else ()),
                )
            },
        }
        version = manifest_version(
            target=target_name,
            algorithm=algorithm,
            dataset_manifest_hash=snapshot.manifest_hash,
            feature_schema_version=snapshot.feature_schema_version,
            parameters=model_parameters,
            code_revision=code_revision,
        )
        evaluation_path = (
            get_settings().artifact_root / "evaluations" / target_name / f"{version}.json"
        )
        write_evaluation(
            evaluation_path,
            {
                "target": target_name,
                "feature_snapshot_id": str(snapshot.id),
                "dataset_manifest_hash": snapshot.manifest_hash,
                "code_revision": code_revision,
                "seasons": unique_seasons.tolist(),
                "holdout_season": holdout_season,
                "training_rows": clean.height,
                "selected_algorithm": algorithm,
                "promoted_over_baseline": promoted,
                "candidate_reports": reports,
                "holdout_metrics": metrics,
                "subgroup_metrics": subgroup_metrics,
                "calibration": calibration,
                "parameters": model_parameters,
            },
        )
        manifest = ModelManifest(
            target=target_name,
            version=version,
            algorithm=algorithm,
            feature_schema_version=snapshot.feature_schema_version,
            feature_names=feature_names,
            dataset_manifest_hash=snapshot.manifest_hash,
            training_cutoff=(snapshot.training_cutoff or snapshot.prediction_cutoff).isoformat(),
            code_revision=code_revision,
            parameters=model_parameters,
            metrics=metrics,
            subgroup_metrics=subgroup_metrics,
            calibration=calibration,
            random_seed=random_seed,
            created_at=datetime.now(UTC).isoformat(),
        )
        registered = LocalModelRegistry(get_settings().artifact_root / "models").register(
            champion_model,
            manifest,
            champion=True,
        )
        await session.execute(
            update(ModelVersion)
            .where(ModelVersion.target == target_name, ModelVersion.status == "champion")
            .values(status="retired")
        )
        existing = await session.scalar(
            select(ModelVersion).where(
                ModelVersion.target == target_name,
                ModelVersion.version == version,
            )
        )
        if existing is None:
            existing = ModelVersion(
                target=target_name,
                version=version,
                algorithm=algorithm,
                status="champion",
                trained_at=datetime.now(UTC),
                training_cutoff=snapshot.training_cutoff or snapshot.prediction_cutoff,
                feature_schema_version=snapshot.feature_schema_version,
                code_revision=code_revision,
                artifact_path=str(registered.artifact_path),
                parameters=manifest.parameters,
                metrics=metrics,
                subgroup_metrics=subgroup_metrics,
                calibration=calibration,
            )
            session.add(existing)
        else:
            existing.status = "champion"
            existing.artifact_path = str(registered.artifact_path)
            existing.metrics = cast(dict[str, object], metrics)
            existing.subgroup_metrics = cast(dict[str, object], subgroup_metrics)
            existing.calibration = calibration
        await session.commit()
        return {
            "model_version_id": str(existing.id),
            "target": target_name,
            "version": version,
            "algorithm": algorithm,
            "promoted_over_baseline": promoted,
            "metrics": metrics,
            "artifact_sha256": registered.artifact_sha256,
            "evaluation_path": str(evaluation_path.resolve()),
        }


def _validated_snapshot_path(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    settings = get_settings()
    allowed = [settings.data_root.resolve(), settings.artifact_root.resolve()]
    if not any(path.is_relative_to(root) for root in allowed):
        raise ValueError()
    if not path.is_file():
        raise ValueError()
    return path


def prepare_target_frame(
    frame: pl.DataFrame,
    target: str,
    label: str,
    season: str,
) -> pl.DataFrame:
    eligible = frame
    if target.startswith("goalkeeper_") and "football_role" in frame.columns:
        eligible = eligible.filter(pl.col("football_role") == "GK")
    if target == "base_rating" and "label_appearance_probability" in frame.columns:
        eligible = eligible.filter(pl.col("label_appearance_probability") == 1)
    coverage = eligible.group_by(season).agg(
        pl.col(label).is_not_null().mean().alias("label_coverage")
    )

    valid_seasons = coverage.filter(pl.col("label_coverage") >= 0.9).select(season)
    return eligible.join(valid_seasons, on=season, how="semi").drop_nulls([label, season])


def _feature_names(
    parameters: dict[str, object],
    defaults: list[str],
) -> tuple[str, ...]:
    value = parameters.get("feature_names")
    if value is None:
        return tuple(defaults)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError()
    if not value:
        raise ValueError()
    return tuple(value)


def _required_uuid(parameters: dict[str, object], key: str) -> uuid.UUID:
    value = _required_string(parameters, key)
    try:
        return uuid.UUID(value)
    except ValueError:
        raise ValueError() from None


def _required_string(parameters: dict[str, object], key: str) -> str:
    value = parameters.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError()
    return value.strip()


def _string(value: object, default: str) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else default


def _integer(value: object, default: int, key: str) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError()
    try:
        return int(value)
    except ValueError:
        raise ValueError() from None
