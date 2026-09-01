from __future__ import annotations

import uuid
from datetime import UTC, datetime

import numpy as np
import polars as pl
import structlog
from sqlalchemy import select

from markguardiola.core.config import get_settings
from markguardiola.db.models import (
    Match,
    ModelVersion,
    PlayerMatchPrediction,
    PredictionRun,
    Season,
)
from markguardiola.db.session import get_session_factory
from markguardiola.features.pipeline import (
    FEATURE_SCHEMA_VERSION,
    build_training_snapshot,
    build_upcoming_snapshot,
)
from markguardiola.features.registry import FeatureRegistry
from markguardiola.ml.arena.candidates import require_external_ml_runtime
from markguardiola.ml.arena.probability import ProbabilityChampion
from markguardiola.ml.arena.regression import RegressionChampion
from markguardiola.ml.registry import LocalModelRegistry
from markguardiola.ml.registry.artifacts import archive_source_code
from markguardiola.ml.targets import TARGETS, ProblemKind
from markguardiola.ml.training import prepare_target_frame, train_from_snapshot
from markguardiola.simulation.rare_events import load_rare_event_prior

logger = structlog.get_logger(__name__)


async def rebuild_models(parameters: dict[str, object]) -> dict[str, object]:
    settings = get_settings()
    archived_as_of = parameters.get("as_of")
    as_of = None
    if archived_as_of is not None:
        if not isinstance(archived_as_of, str):
            raise ValueError()
        as_of = datetime.fromisoformat(archived_as_of)
        if as_of.tzinfo is None:
            raise ValueError()
    if parameters.get("include_external", True):
        require_external_ml_runtime()
    code_revision = archive_source_code(settings.artifact_root)
    async with get_session_factory()() as session:
        prepared = (
            await build_training_snapshot(session, settings, as_of=as_of)
            if as_of is not None
            else await build_training_snapshot(session, settings)
        )
    registry = FeatureRegistry.load()
    requested = parameters.get("targets")
    target_names = (
        [item for item in requested if isinstance(item, str)]
        if isinstance(requested, list)
        else list(TARGETS)
    )
    trained: list[dict[str, object]] = []
    skipped: dict[str, str] = {}
    for target_name in target_names:
        if target_name not in TARGETS:
            skipped[target_name] = "unknown target"
            continue
        label = f"label_{target_name}"
        if label not in prepared.frame.columns:
            skipped[target_name] = "source does not provide a supported label"
            continue
        labeled = prepare_target_frame(prepared.frame, target_name, label, "season")
        if labeled.height < 100 or labeled["season"].n_unique() < 4:
            skipped[target_name] = "not enough labeled rows across four chronological seasons"
            continue
        if TARGETS[target_name].kind == ProblemKind.PROBABILITY and labeled[label].n_unique() < 2:
            skipped[target_name] = "historical labels contain only one outcome class"
            continue
        feature_names = [
            item.name
            for item in registry.for_target(target_name)
            if item.name in prepared.frame.columns
            and labeled[item.name].null_count() < labeled.height
        ]
        if not feature_names:
            skipped[target_name] = "no registered features are available for this target"
            continue
        logger.info(
            "model_target_training",
            target=target_name,
            rows=labeled.height,
            seasons=labeled["season"].n_unique(),
            features=len(feature_names),
        )
        trained.append(
            await train_from_snapshot(
                {
                    "feature_snapshot_id": str(prepared.metadata.id),
                    "target": target_name,
                    "label_column": label,
                    "season_column": "season",
                    "feature_names": feature_names,
                    "subgroup_column": "football_role",
                    "include_external": parameters.get("include_external", True),
                    "random_seed": parameters.get("random_seed", 2026),
                    "code_revision": code_revision,
                }
            )
        )
        logger.info("model_target_registered", **trained[-1])
    if not trained:
        raise ValueError()
    try:
        prediction_result = (
            await predict_upcoming(cutoff=as_of) if as_of is not None else await predict_upcoming()
        )
    except ValueError:
        prediction_result = {"status": "unavailable"}
    return {
        "feature_snapshot_id": str(prepared.metadata.id),
        "trained_models": trained,
        "skipped_targets": skipped,
        "prediction_run": prediction_result,
    }


async def predict_upcoming(*, cutoff: datetime | None = None) -> dict[str, object]:
    settings = get_settings()
    registry = LocalModelRegistry(settings.artifact_root / "models")
    async with get_session_factory()() as session:
        model_versions = list(
            (
                await session.scalars(
                    select(ModelVersion)
                    .where(ModelVersion.status == "champion")
                    .order_by(ModelVersion.trained_at)
                )
            ).all()
        )
        by_target = {model.target: model for model in model_versions}
        if not by_target:
            raise ValueError()
        incompatible = [
            name
            for name, version in by_target.items()
            if version.feature_schema_version != FEATURE_SCHEMA_VERSION
        ]
        if incompatible:
            raise ValueError()
        prepared = (
            await build_upcoming_snapshot(session, settings, cutoff=cutoff)
            if cutoff is not None
            else await build_upcoming_snapshot(session, settings)
        )
        frame = prepared.frame
        competitions = (
            await session.scalars(
                select(Season.competition_id)
                .join(Match, Match.season_id == Season.id)
                .where(Match.id.in_([uuid.UUID(value) for value in frame["match_id"].unique()]))
                .distinct()
            )
        ).all()
        simulation_priors: dict[str, object] = {}
        for competition_id in competitions:
            prior = await load_rare_event_prior(
                session,
                competition_id=competition_id,
                cutoff=prepared.metadata.prediction_cutoff,
            )
            simulation_priors[str(competition_id)] = prior.to_document()
        run = PredictionRun(
            prediction_cutoff=prepared.metadata.prediction_cutoff,
            data_cutoff=prepared.metadata.prediction_cutoff,
            model_versions={target: version.version for target, version in by_target.items()},
            feature_snapshot_id=prepared.metadata.id,
            status="running",
            simulation_priors=simulation_priors,
            code_revision=archive_source_code(settings.artifact_root),
        )
        session.add(run)
        await session.flush()
        predictions: list[PlayerMatchPrediction] = []
        player_ids = frame["player_id"].to_list()
        match_ids = frame["match_id"].to_list()
        team_ids = frame["team_id"].to_list()
        football_roles = frame["football_role"].to_list()
        for target_name, model_version in by_target.items():
            champion, _manifest = registry.load_champion(target_name)
            if _manifest["version"] != model_version.version:
                raise ValueError()
            if not isinstance(champion, (ProbabilityChampion, RegressionChampion)):
                raise TypeError()
            features = np.asarray(
                frame.select(champion.feature_names).cast(pl.Float64, strict=False).to_numpy(),
                dtype=np.float64,
            )
            if isinstance(champion, ProbabilityChampion):
                values = champion.predict_proba(features)
                lower = np.where(values >= 0.9, 1.0, 0.0)
                upper = np.where(values > 0.1, 1.0, 0.0)
                medians = np.where(values >= 0.5, 1.0, 0.0)
                reliability = max(
                    0.0, min(1.0, 1.0 - champion.metrics.get("calibration_error", 0.2))
                )
                kind = "bernoulli"
            else:
                values = champion.predict(features)
                interval = champion.interval.predict(values)
                lower = interval.lower
                upper = interval.upper
                medians = values
                error = champion.metrics.get("mae", champion.metrics.get("poisson_deviance", 1.0))
                reliability = 1.0 / (1.0 + max(error, 0.0))
                kind = "conformal_regression"
            for index, (player_id, match_id) in enumerate(zip(player_ids, match_ids, strict=True)):
                predictions.append(
                    PlayerMatchPrediction(
                        prediction_run_id=run.id,
                        match_id=uuid.UUID(str(match_id)),
                        player_id=uuid.UUID(str(player_id)),
                        target=target_name,
                        expected_value=float(values[index]),
                        median=float(medians[index]),
                        p10=float(lower[index]),
                        p90=float(upper[index]),
                        probability=(float(values[index]) if kind == "bernoulli" else None),
                        reliability=reliability,
                        distribution={
                            "kind": kind,
                            "model_version": model_version.version,
                            "feature_snapshot_id": str(prepared.metadata.id),
                            "team_id": team_ids[index],
                            "football_role": football_roles[index],
                        },
                        model_version_id=model_version.id,
                    )
                )
        _enforce_probability_coherence(predictions)
        session.add_all(predictions)
        run.status = "succeeded"
        await session.commit()
        return {
            "status": "succeeded",
            "prediction_run_id": str(run.id),
            "player_fixture_count": frame.height,
            "prediction_count": len(predictions),
            "generated_at": datetime.now(UTC).isoformat(),
        }


def _enforce_probability_coherence(predictions: list[PlayerMatchPrediction]) -> None:
    grouped: dict[tuple[uuid.UUID, uuid.UUID], dict[str, PlayerMatchPrediction]] = {}
    for prediction in predictions:
        grouped.setdefault((prediction.player_id, prediction.match_id), {})[prediction.target] = (
            prediction
        )
    for values in grouped.values():
        for probability_target, upper_target in (
            ("start_probability", "appearance_probability"),
            ("goal_probability", "expected_goals"),
            ("assist_probability", "expected_assists"),
        ):
            probability = values.get(probability_target)
            upper = values.get(upper_target)
            if probability is None or upper is None:
                continue
            bounded = min(probability.expected_value, upper.expected_value, 1.0)
            if bounded < probability.expected_value:
                probability.distribution = {
                    **probability.distribution,
                    "coherence_upper_bound": upper_target,
                    "unconstrained_probability": probability.expected_value,
                }
                probability.expected_value = bounded
                probability.probability = bounded
                probability.median = float(bounded >= 0.5)
                probability.p10 = float(bounded >= 0.9)
                probability.p90 = float(bounded > 0.1)
