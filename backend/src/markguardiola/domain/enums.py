from enum import StrEnum


class KickoffPrecision(StrEnum):
    UNKNOWN = "unknown"
    DATE = "date"
    MINUTE = "minute"


class EntityType(StrEnum):
    COMPETITION = "competition"
    SEASON = "season"
    TEAM = "team"
    PLAYER = "player"
    COACH = "coach"
    REFEREE = "referee"
    VENUE = "venue"
    MATCH = "match"


class IngestionStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"


class QualitySeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    BLOCKING = "blocking"


class ResolutionMethod(StrEnum):
    EXISTING_MAPPING = "existing_mapping"
    EXACT = "exact"
    FUZZY = "fuzzy"
    TEMPORAL_CONTEXT = "temporal_context"
    MANUAL = "manual"


class LeagueMode(StrEnum):
    CLASSIC = "classic"
    MANTRA = "mantra"


class RiskMode(StrEnum):
    BALANCED = "balanced"
    FLOOR = "floor"
    UPSIDE = "upside"
    MATCHUP = "matchup"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ModelStatus(StrEnum):
    CANDIDATE = "candidate"
    CHAMPION = "champion"
    RETIRED = "retired"
