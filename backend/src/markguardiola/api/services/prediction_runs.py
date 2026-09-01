import uuid

from sqlalchemy import select, true
from sqlalchemy.ext.asyncio import AsyncSession

from markguardiola.api.services.fixture_simulations import PredictionDataUnavailableError
from markguardiola.db.models import (
    FeatureSnapshotMetadata,
    ModelVersion,
    PlayerMatchPrediction,
    PredictionRun,
)
from markguardiola.features.pipeline import FEATURE_SCHEMA_VERSION


async def latest_compatible_prediction_run(
    session: AsyncSession, *, run_id: uuid.UUID | None = None
) -> PredictionRun:
    run = await session.scalar(
        select(PredictionRun)
        .where(PredictionRun.status == "succeeded")
        .where(PredictionRun.id == run_id if run_id is not None else true())
        .order_by(PredictionRun.prediction_cutoff.desc())
        .limit(1)
    )
    if run is None:
        raise PredictionDataUnavailableError()
    snapshot = await session.get(FeatureSnapshotMetadata, run.feature_snapshot_id)
    if (
        snapshot is None
        or snapshot.feature_schema_version != FEATURE_SCHEMA_VERSION
        or snapshot.prediction_cutoff != run.prediction_cutoff
        or run.data_cutoff > run.prediction_cutoff
    ):
        raise PredictionDataUnavailableError()
    references = (
        select(PlayerMatchPrediction.target, PlayerMatchPrediction.model_version_id)
        .where(PlayerMatchPrediction.prediction_run_id == run.id)
        .distinct()
        .subquery()
    )
    models = (
        await session.execute(
            select(references.c.target, ModelVersion).join(
                ModelVersion, ModelVersion.id == references.c.model_version_id
            )
        )
    ).all()
    incompatible = {
        target
        for target, model in models
        if (
            model.target != target
            or run.model_versions.get(target) != model.version
            or model.feature_schema_version != FEATURE_SCHEMA_VERSION
            or model.trained_at > run.prediction_cutoff
            or model.training_cutoff > run.data_cutoff
            or not _compatible_features(model.parameters.get("feature_names", []), snapshot)
        )
    }
    incompatible.update(
        set(run.model_versions).symmetric_difference(target for target, _ in models)
    )
    if not models or incompatible:
        raise PredictionDataUnavailableError()
    return run


def _compatible_features(value: object, snapshot: FeatureSnapshotMetadata) -> bool:
    return (
        isinstance(value, list)
        and all(isinstance(item, str) for item in value)
        and set(value).issubset(snapshot.feature_names)
    )
