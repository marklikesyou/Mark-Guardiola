from markguardiola.entity_resolution.normalization import normalize_name
from markguardiola.entity_resolution.resolver import (
    EntityResolver,
    IdentityCandidate,
    IdentityQuery,
    ResolutionResult,
    ResolutionStatus,
)

__all__ = [
    "EntityResolver",
    "IdentityCandidate",
    "IdentityQuery",
    "ResolutionResult",
    "ResolutionStatus",
    "normalize_name",
]
