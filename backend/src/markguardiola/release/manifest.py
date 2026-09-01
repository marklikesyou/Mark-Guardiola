from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from markguardiola.db import models as _models
from markguardiola.db.base import Base

del _models


FOOTBALL_TABLES = frozenset(
    {
        "data_sources",
        "schema_versions",
        "ingestion_runs",
        "raw_objects",
        "provider_entity_map",
        "data_quality_issues",
        "competitions",
        "seasons",
        "teams",
        "players",
        "coaches",
        "referees",
        "venues",
        "player_team_periods",
        "matches",
        "lineups",
        "player_match_stats",
        "team_match_stats",
        "team_standing_snapshots",
        "events",
        "shots",
        "injuries",
        "suspensions",
        "transfers",
        "odds_snapshots",
        "feature_snapshot_metadata",
        "model_versions",
        "prediction_runs",
        "player_match_predictions",
    }
)
REQUIRED_TABLES = frozenset(
    {
        "players",
        "matches",
        "player_match_stats",
        "lineups",
        "shots",
        "events",
        "feature_snapshot_metadata",
        "model_versions",
        "prediction_runs",
        "player_match_predictions",
    }
)
BLOCK_SIZE = 1024 * 1024


RAW_INPUT_TABLES = frozenset(
    {
        "data_sources",
        "schema_versions",
        "ingestion_runs",
        "raw_objects",
        "provider_entity_map",
        "competitions",
        "seasons",
        "teams",
        "players",
        "coaches",
        "referees",
        "venues",
    }
)
SHA256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class BinaryReader(Protocol):
    def read(self, size: int = -1, /) -> bytes: ...


class FileRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    size: int = Field(ge=0, le=100 * 1024**3)
    sha256: SHA256


class BundleManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    format_version: Literal[1] = 1
    model_scope: Literal["champions-and-latest-predictions"] = "champions-and-latest-predictions"
    version: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
    application_version: str
    created_at: str
    reconstruction_cutoff: str | None = None
    postgres_major: int = Field(ge=17, le=17)
    migration_head: str
    feature_schema: str
    lock_sha256: SHA256
    source_revision: SHA256
    columns: dict[str, list[str]]
    row_counts: dict[str, Annotated[int, Field(ge=0)]]
    champions: dict[str, str]
    files: dict[str, FileRecord]

    paths: dict[str, dict[str, str]]

    @field_validator("created_at", "reconstruction_cutoff")
    @classmethod
    def require_aware_timestamp(cls, value: str | None) -> str | None:
        if value is not None and datetime.fromisoformat(value).tzinfo is None:
            raise ValueError()
        return value

    @property
    def replay_cutoff(self) -> datetime:

        return datetime.fromisoformat(self.reconstruction_cutoff or self.created_at)

    @model_validator(mode="after")
    def cutoff_precedes_export(self) -> BundleManifest:
        if self.replay_cutoff > datetime.fromisoformat(self.created_at):
            raise ValueError()
        return self


def table_columns() -> dict[str, list[str]]:
    return {
        table.name: [column.name for column in table.columns]
        for table in Base.metadata.sorted_tables
        if table.name in FOOTBALL_TABLES
    }


def safe_path(name: str) -> PurePosixPath:

    path = PurePosixPath(name)
    if (
        not name
        or path.is_absolute()
        or path.as_posix() != name
        or any(
            part.startswith(".") or re.search(r'[\x00-\x1f:<>"|?*\\]', part) for part in path.parts
        )
        or any(part.endswith((".", " ")) for part in path.parts)
    ):
        raise ValueError()
    if any(
        re.fullmatch(r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", p) for p in path.parts
    ):
        raise ValueError()
    return path


def file_record(stream: BinaryReader) -> FileRecord:
    digest = hashlib.sha256()
    size = 0
    while block := stream.read(BLOCK_SIZE):
        digest.update(block)
        size += len(block)
    return FileRecord(size=size, sha256=digest.hexdigest())


def path_record(path: Path) -> FileRecord:
    with path.open("rb") as stream:
        return file_record(stream)


def dependency_hash() -> str:
    return path_record(Path(__file__).resolve().parents[3] / "uv.lock").sha256
