from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from markguardiola.ingestion.contracts import RawPayload


@dataclass(frozen=True, slots=True)
class StoredRawObject:
    content_sha256: str
    relative_path: str
    content_bytes: int
    duplicate: bool


class RawObjectStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def persist(
        self,
        *,
        provider: str,
        run_id: str,
        payload: RawPayload,
        competition: str,
        season: str | None = None,
    ) -> StoredRawObject:
        digest = hashlib.sha256(payload.content).hexdigest()
        timestamp = payload.retrieved_at.astimezone(UTC)
        suffix = _suffix_for_media_type(payload.media_type)
        parts = [
            _safe_segment(provider),
            _safe_segment(competition),
            _safe_segment(season or "unscoped"),
            timestamp.strftime("%Y-%m-%d"),
            _safe_segment(run_id),
        ]
        directory = self._root.joinpath(*parts)
        directory.mkdir(parents=True, exist_ok=True)
        object_path = directory / f"{digest}{suffix}"
        duplicate = object_path.exists()
        if not duplicate:
            _atomic_write(object_path, payload.content)

        relative = str(object_path.relative_to(self._root))
        manifest_path = object_path.with_suffix(object_path.suffix + ".metadata.json")
        if not manifest_path.exists():
            metadata = {
                "provider_object_id": payload.provider_object_id,
                "request_url": payload.request_url,
                "request_params": payload.request_params,
                "media_type": payload.media_type,
                "content_sha256": digest,
                "content_bytes": len(payload.content),
                "event_time": _iso(payload.event_time),
                "available_at": _iso(payload.available_at),
                "retrieved_at": _iso(payload.retrieved_at),
                "response_headers": payload.response_headers,
                "schema_hint": payload.schema_hint,
            }
            _atomic_write(
                manifest_path,
                json.dumps(metadata, sort_keys=True, indent=2).encode("utf-8"),
            )

        return StoredRawObject(
            content_sha256=digest,
            relative_path=relative,
            content_bytes=len(payload.content),
            duplicate=duplicate,
        )


def write_run_manifest(path: Path, objects: list[StoredRawObject]) -> None:
    manifest = {
        "created_at": datetime.now(UTC).isoformat(),
        "objects": [asdict(obj) for obj in sorted(objects, key=lambda item: item.relative_path)],
    }
    _atomic_write(path, json.dumps(manifest, sort_keys=True, indent=2).encode("utf-8"))


def _atomic_write(path: Path, content: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_bytes(content)
    temporary.replace(path)


def _safe_segment(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_", "."} else "-" for char in value)
    cleaned = cleaned.strip("-.")
    if not cleaned or cleaned in {".", ".."}:
        raise ValueError()
    return cleaned[:160]


def _suffix_for_media_type(media_type: str) -> str:
    normalized = media_type.split(";", maxsplit=1)[0].strip().lower()
    return {
        "application/json": ".json",
        "text/csv": ".csv",
        "application/csv": ".csv",
        "application/vnd.apache.parquet": ".parquet",
        "application/octet-stream": ".bin",
    }.get(normalized, ".raw")


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat() if value is not None else None
