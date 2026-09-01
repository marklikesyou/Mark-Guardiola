from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from importlib.metadata import version
from pathlib import Path

import joblib
import numpy as np
import polars as pl
import structlog

from markguardiola.features.registry import FeatureRegistry
from markguardiola.ml.arena import (
    ProbabilityModelArena,
    RegressionModelArena,
    probability_candidates,
    regression_candidates,
)
from markguardiola.ml.arena.candidates import require_external_ml_runtime
from markguardiola.ml.arena.probability import ProbabilityChampion
from markguardiola.ml.arena.regression import RegressionChampion
from markguardiola.ml.targets import ProblemKind, target_definition
from markguardiola.ml.training import prepare_target_frame

logger = structlog.get_logger(__name__)
REPLAY_TARGETS = (
    "start_probability",
    "appearance_probability",
    "expected_minutes",
    "expected_goals",
    "expected_assists",
    "team_goals",
    "yellow_card_probability",
    "red_card_probability",
    "goalkeeper_saves",
)


@dataclass(frozen=True, slots=True)
class ReplayModel:
    champion: ProbabilityChampion | RegressionChampion
    recipe_id: str
    manifest: dict[str, object]


def train_replay_models(
    frame: pl.DataFrame,
    *,
    cutoff: datetime,
    snapshot_hash: str,
    source_revision: str,
    root: Path,
    include_external: bool = True,
    seed: int = 2026,
) -> dict[str, ReplayModel]:

    latest = None if frame.is_empty() else frame["prediction_cutoff"].max()
    if not isinstance(latest, datetime) or latest >= cutoff:
        raise ValueError()
    if include_external:
        require_external_ml_runtime()
    dependencies = {
        name: version(name)
        for name in (
            "numpy",
            "polars",
            "scikit-learn",
            "scipy",
            *(("lightgbm", "xgboost", "catboost") if include_external else ()),
        )
    }
    registry = FeatureRegistry.load()
    implementation = _implementation_digest()
    models: dict[str, ReplayModel] = {}
    for target in REPLAY_TARGETS:
        label = f"label_{target}"
        clean = prepare_target_frame(frame, target, label, "season")
        if target == "team_goals":
            clean = clean.unique(subset=["team_id", "match_id"], maintain_order=True)
        names = tuple(
            item.name
            for item in registry.for_target(target)
            if item.name in clean.columns and clean[item.name].null_count() < clean.height
        )
        if clean.height < 100 or clean["season"].n_unique() < 4 or not names:
            raise ValueError()
        recipe = {
            "target": target,
            "cutoff": cutoff.isoformat(),
            "snapshot_sha256": snapshot_hash,
            "features": names,
            "seed": seed,
            "dependencies": dependencies,
            "implementation_sha256": implementation,
        }
        recipe_id = hashlib.sha256(json.dumps(recipe, sort_keys=True).encode()).hexdigest()
        destination = root / recipe_id
        manifest_path = destination / "manifest.json"
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text())
            artifact = destination / str(manifest["artifact"])
            if hashlib.sha256(artifact.read_bytes()).hexdigest() != manifest["artifact_sha256"]:
                raise ValueError()
            champion = joblib.load(artifact)
            if not isinstance(champion, (ProbabilityChampion, RegressionChampion)):
                raise ValueError()
            models[target] = ReplayModel(champion, recipe_id, manifest)
            logger.info("replay_model_reused", target=target, recipe_id=recipe_id)
            continue
        logger.info("replay_model_training", target=target, rows=clean.height)
        features = np.asarray(clean.select(names).cast(pl.Float64).to_numpy(), dtype=float)
        labels = np.asarray(clean[label].to_numpy(), dtype=float)
        seasons = np.asarray(clean["season"].to_numpy(), dtype=str)
        subgroups = (
            None if target == "team_goals" else np.asarray(clean["football_role"].to_numpy())
        )
        definition = target_definition(target)
        if definition.kind == ProblemKind.PROBABILITY:
            probability_result = ProbabilityModelArena(
                probability_candidates(random_seed=seed, include_external=include_external)
            ).run(
                features=features,
                target=labels,
                seasons=seasons,
                feature_names=names,
                subgroups=subgroups,
            )
            champion = probability_result.champion
            reports = [asdict(report) for report in probability_result.reports]
        else:
            count = definition.kind == ProblemKind.COUNT
            regression_result = RegressionModelArena(
                regression_candidates(
                    random_seed=seed, count=count, include_external=include_external
                ),
                count=count,
                lower_bound=definition.lower_bound,
                upper_bound=definition.upper_bound,
            ).run(
                features=features,
                target=labels,
                seasons=seasons,
                feature_names=names,
                subgroups=subgroups,
            )
            champion = regression_result.champion
            reports = [asdict(report) for report in regression_result.reports]
        destination.mkdir(parents=True, exist_ok=True)
        temporary = destination / ".model.joblib"
        joblib.dump(champion, temporary, compress=3)
        digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
        artifact = destination / f"model-{digest}.joblib"
        temporary.replace(artifact)
        manifest = {
            **recipe,
            "source_revision": source_revision,
            "artifact": artifact.name,
            "artifact_sha256": digest,
            "fit_seasons": sorted(set(seasons))[:-1],
            "calibration_season": sorted(set(seasons))[-1],
            "candidate_reports": reports,
            "selected_algorithm": champion.candidate_name,
            "pre_replay_holdout_metrics": champion.metrics,
        }
        temporary_manifest = destination / ".manifest.json"
        temporary_manifest.write_text(json.dumps(manifest, sort_keys=True, indent=2))
        temporary_manifest.replace(manifest_path)
        models[target] = ReplayModel(champion, recipe_id, manifest)
        logger.info("replay_model_complete", target=target, algorithm=champion.candidate_name)
    return models


def _implementation_digest() -> str:
    package = Path(__file__).resolve().parents[1]
    paths = [Path(__file__), *sorted((package / "ml").rglob("*.py"))]
    digest = hashlib.sha256()
    for path in paths:
        digest.update(str(path.relative_to(package)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()
