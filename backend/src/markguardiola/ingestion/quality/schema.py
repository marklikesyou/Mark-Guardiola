from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import dataclass

import pyarrow.parquet as pq

from markguardiola.ingestion.contracts import RawPayload


@dataclass(frozen=True, slots=True)
class SchemaFingerprint:
    version_hint: str
    digest: str
    fields: tuple[str, ...]


def fingerprint_payload(payload: RawPayload) -> SchemaFingerprint:
    media_type = payload.media_type.lower()
    fields: tuple[str, ...]
    type_signature: str = ""
    if media_type == "application/json":
        parsed = json.loads(payload.content)
        fields = tuple(sorted(_json_shape(parsed)))
    elif media_type in {"text/csv", "application/csv"}:
        reader = csv.reader(io.StringIO(payload.content.decode("utf-8-sig")))
        fields = tuple(next(reader, []))
    elif media_type == "application/vnd.apache.parquet" or (
        payload.content.startswith(b"PAR1") and payload.content.endswith(b"PAR1")
    ):
        schema = pq.read_schema(io.BytesIO(payload.content))
        fields = tuple(field.name for field in schema)
        type_signature = "\n".join(
            f"{field.name}:{field.type}:{field.nullable}" for field in schema
        )
    else:
        fields = (f"content-type:{media_type}",)
    digest = hashlib.sha256(("\n".join(fields) + type_signature).encode("utf-8")).hexdigest()
    return SchemaFingerprint(
        version_hint=payload.schema_hint or "unversioned",
        digest=digest,
        fields=fields,
    )


def _json_shape(value: object, prefix: str = "$") -> set[str]:
    if isinstance(value, dict):
        fields = {f"{prefix}.{key}" for key in value}
        for key, child in value.items():
            if isinstance(child, (dict, list)):
                fields.update(_json_shape(child, f"{prefix}.{key}"))
        return fields
    if isinstance(value, list):
        if not value:
            return {f"{prefix}[]"}
        return _json_shape(value[0], f"{prefix}[]")
    return {prefix}
