from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, time

import polars as pl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from markguardiola.backtesting.models import ReplayModel, train_replay_models
from markguardiola.core.config import Settings, get_settings
from markguardiola.db.models import Season
from markguardiola.db.session import get_session_factory
from markguardiola.features.builders import PointInTimeSnapshotBuilder
from markguardiola.features.materialize import materialize_snapshot
from markguardiola.features.pipeline import FEATURE_SCHEMA_VERSION, load_canonical_history
from markguardiola.ml.registry.artifacts import archive_source_code


@dataclass(frozen=True, slots=True)
class ReplayTraining:
    season: Season
    cutoff: datetime
    frame: pl.DataFrame
    models: dict[str, ReplayModel]
    snapshot_hash: str
    source_revision: str


async def prepare_replay_training(
    session: AsyncSession,
    settings: Settings,
    *,
    season_label: str,
    include_external: bool = True,
    training_snapshot_hash: str | None = None,
) -> ReplayTraining:
    seasons = (await session.scalars(select(Season).where(Season.label == season_label))).all()
    if len(seasons) != 1:
        raise ValueError()
    season = seasons[0]
    if season.end_date >= datetime.now(UTC).date():
        raise ValueError()
    cutoff = datetime.combine(season.start_date, time.min, tzinfo=UTC)
    if training_snapshot_hash is not None:
        frame = _load_training_snapshot(settings, training_snapshot_hash, cutoff, season_label)
        snapshot_hash = training_snapshot_hash
    else:
        history = await load_canonical_history(session, cutoff=cutoff)
        frame = (
            PointInTimeSnapshotBuilder()
            .build(
                candidates=history.training_candidates,
                player_history=history.player_history,
                team_history=history.team_history,
            )
            .join(history.labels, on="snapshot_row_id", how="left")
        )
        materialized = materialize_snapshot(
            frame,
            output_root=settings.artifact_root / "backtests" / "training",
            feature_schema_version=FEATURE_SCHEMA_VERSION,
            source_manifest={
                "kind": "historical_decision_replay_training",
                "cutoff": cutoff.isoformat(),
                "evaluation_season": season_label,
                "ingestion_run_ids": list(history.ingestion_run_ids),
            },
        )
        snapshot_hash = materialized.content_sha256
    source_revision = archive_source_code(settings.artifact_root)
    models = await asyncio.to_thread(
        train_replay_models,
        frame,
        cutoff=cutoff,
        snapshot_hash=snapshot_hash,
        source_revision=source_revision,
        root=settings.artifact_root / "backtests" / "models",
        include_external=include_external,
    )
    return ReplayTraining(season, cutoff, frame, models, snapshot_hash, source_revision)


def _load_training_snapshot(
    settings: Settings, digest: str, cutoff: datetime, season_label: str
) -> pl.DataFrame:
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ValueError()
    path = (
        settings.artifact_root
        / "backtests"
        / "training"
        / FEATURE_SCHEMA_VERSION
        / f"{digest}.parquet"
    )
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError()
    manifest = json.loads(path.with_suffix(".manifest.json").read_text())
    source = manifest["source_manifest"]
    if (
        source.get("kind") != "historical_decision_replay_training"
        or source.get("cutoff") != cutoff.isoformat()
        or source.get("evaluation_season") != season_label
    ):
        raise ValueError()
    return pl.read_parquet(path)


async def train_historical_models(
    season_label: str, *, include_external: bool = True
) -> dict[str, object]:
    async with get_session_factory()() as session:
        training = await prepare_replay_training(
            session, get_settings(), season_label=season_label, include_external=include_external
        )
    return {
        "evaluation_season": season_label,
        "training_cutoff": training.cutoff.isoformat(),
        "snapshot_sha256": training.snapshot_hash,
        "source_revision": training.source_revision,
        "models": {
            target: {"recipe_id": model.recipe_id, "algorithm": model.champion.candidate_name}
            for target, model in training.models.items()
        },
        "production_registry_modified": False,
    }
