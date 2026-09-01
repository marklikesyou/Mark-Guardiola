from __future__ import annotations

import hashlib
import json
import os
import uuid
import zipfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib


@dataclass(frozen=True, slots=True)
class ModelManifest:
    target: str
    version: str
    algorithm: str
    feature_schema_version: str
    feature_names: tuple[str, ...]
    dataset_manifest_hash: str
    training_cutoff: str
    code_revision: str | None
    parameters: dict[str, object]
    metrics: dict[str, float]
    subgroup_metrics: dict[str, dict[str, float]]
    calibration: dict[str, object]
    random_seed: int
    created_at: str


@dataclass(frozen=True, slots=True)
class RegisteredModel:
    artifact_path: Path
    manifest_path: Path
    artifact_sha256: str


class LocalModelRegistry:
    def __init__(self, root: Path) -> None:
        self._root = root

    def register(
        self, model: Any, manifest: ModelManifest, *, champion: bool = False
    ) -> RegisteredModel:
        directory = self._root / manifest.target / manifest.version
        directory.mkdir(parents=True, exist_ok=True)
        temporary = directory / f".model-{os.getpid()}.joblib"
        joblib.dump(model, temporary, compress=3)
        digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
        artifact = directory / f"model-{digest}.joblib"
        if artifact.exists():
            temporary.unlink()
        else:
            temporary.replace(artifact)
        manifest_path = directory / "manifest.json"
        _atomic_json(manifest_path, asdict(manifest))
        if champion:
            pointer = self._root / manifest.target / "champion.json"
            _atomic_json(
                pointer,
                {
                    "version": manifest.version,
                    "artifact": str(artifact.relative_to(self._root)),
                    "manifest": str(manifest_path.relative_to(self._root)),
                    "promoted_at": datetime.now(UTC).isoformat(),
                },
            )
        return RegisteredModel(artifact, manifest_path, digest)

    def load_champion(self, target: str) -> tuple[Any, dict[str, object]]:
        pointer_path = self._root / target / "champion.json"
        if not pointer_path.exists():
            raise FileNotFoundError()
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        artifact = self._root / pointer["artifact"]
        manifest_path = self._root / pointer["manifest"]
        expected_digest = artifact.stem.removeprefix("model-")
        actual_digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        if actual_digest != expected_digest:
            raise RuntimeError()
        return joblib.load(artifact), json.loads(manifest_path.read_text(encoding="utf-8"))


def manifest_version(
    *,
    target: str,
    algorithm: str,
    dataset_manifest_hash: str,
    feature_schema_version: str,
    parameters: dict[str, object] | None = None,
    code_revision: str | None = None,
) -> str:
    value = json.dumps(
        {
            "target": target,
            "algorithm": algorithm,
            "dataset": dataset_manifest_hash,
            "feature_schema": feature_schema_version,
            "parameters": parameters or {},
            "code_revision": code_revision,
        },
        sort_keys=True,
    )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def source_code_revision() -> str:

    return _source_digest(_source_files())


def archive_source_code(artifact_root: Path) -> str:

    files = _source_files()
    revision = _source_digest(files)
    directory = artifact_root / "source"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{revision}.zip"
    if not path.exists():
        temporary = directory / f".{revision}.{uuid.uuid4().hex}.zip"
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content in files.items():
                entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(entry, content)
        temporary.replace(path)
    return revision


def _source_files() -> dict[str, bytes]:
    root = Path(__file__).resolve().parents[2]
    files = {
        f"backend/src/markguardiola/{path.relative_to(root).as_posix()}": path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.suffix in {".py", ".json"}
    }
    for filename in ("pyproject.toml", "uv.lock"):
        path = root.parents[1] / filename
        if path.is_file():
            files[f"backend/{filename}"] = path.read_bytes()
    return dict(sorted(files.items()))


def _source_digest(files: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    for name, content in files.items():
        digest.update(name.encode())
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def write_evaluation(path: Path, report: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_json(path, report)


def _atomic_json(path: Path, value: object) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2), encoding="utf-8")
    temporary.replace(path)
