import json
import uuid


def fact_id(source: str, table: str, provider_record_id: str, *, deterministic: bool) -> uuid.UUID:
    if not deterministic:
        return uuid.uuid4()
    name = json.dumps(["markguardiola:source-fact:v1", source, table, provider_record_id])
    return uuid.uuid5(uuid.NAMESPACE_URL, name)
