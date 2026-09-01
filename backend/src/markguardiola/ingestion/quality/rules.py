from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol

from markguardiola.domain.enums import QualitySeverity
from markguardiola.ingestion.contracts import CanonicalMatchRecord, CanonicalPlayerMatchRecord


@dataclass(frozen=True, slots=True)
class QualityFinding:
    rule_key: str
    severity: QualitySeverity
    message: str
    source_record_id: str | None = None
    evidence: dict[str, object] = field(default_factory=dict)


class MatchQualityRule(Protocol):
    key: str

    def check(self, records: list[CanonicalMatchRecord]) -> list[QualityFinding]: ...


class DistinctMatchTeamsRule:
    key = "match.distinct_teams"

    def check(self, records: list[CanonicalMatchRecord]) -> list[QualityFinding]:
        return [
            QualityFinding(
                rule_key=self.key,
                severity=QualitySeverity.BLOCKING,
                message="A match must contain two distinct teams.",
                source_record_id=record.source_record_id,
            )
            for record in records
            if record.home_team_provider_id == record.away_team_provider_id
            or record.home_team_name.casefold() == record.away_team_name.casefold()
        ]


class DuplicateMatchRule:
    key = "match.duplicate_source_record"

    def check(self, records: list[CanonicalMatchRecord]) -> list[QualityFinding]:
        counts = Counter(record.source_record_id for record in records)
        return [
            QualityFinding(
                rule_key=self.key,
                severity=QualitySeverity.BLOCKING,
                message="Duplicate provider match record detected.",
                source_record_id=source_id,
                evidence={"count": count},
            )
            for source_id, count in counts.items()
            if count > 1
        ]


class ScoreConsistencyRule:
    key = "match.score_consistency"

    def check(self, records: list[CanonicalMatchRecord]) -> list[QualityFinding]:
        findings: list[QualityFinding] = []
        for record in records:
            finished = record.status.lower() in {"finished", "ft", "aet", "pen"}
            has_scores = record.home_score is not None and record.away_score is not None
            if finished != has_scores:
                findings.append(
                    QualityFinding(
                        rule_key=self.key,
                        severity=QualitySeverity.ERROR,
                        message="Finished state and score presence disagree.",
                        source_record_id=record.source_record_id,
                        evidence={"status": record.status},
                    )
                )
            if any(
                score is not None and score < 0 for score in (record.home_score, record.away_score)
            ):
                findings.append(
                    QualityFinding(
                        rule_key=self.key,
                        severity=QualitySeverity.BLOCKING,
                        message="A match score cannot be negative.",
                        source_record_id=record.source_record_id,
                    )
                )
        return findings


class MissingCurrentFixtureRule:
    key = "fixture.missing_current_schedule"

    def __init__(self, now: datetime, horizon: timedelta = timedelta(days=21)) -> None:
        self._now = now
        self._horizon = horizon

    def check(self, records: list[CanonicalMatchRecord]) -> list[QualityFinding]:
        upcoming = [
            record
            for record in records
            if self._now <= record.kickoff_at <= self._now + self._horizon
        ]
        if upcoming:
            return []
        return [
            QualityFinding(
                rule_key=self.key,
                severity=QualitySeverity.WARNING,
                message="No upcoming fixture is available in the configured horizon.",
                evidence={"horizon_days": self._horizon.days},
            )
        ]


def validate_player_match_records(
    records: list[CanonicalPlayerMatchRecord],
) -> list[QualityFinding]:
    findings: list[QualityFinding] = []
    for record in records:
        for metric in ("xg", "xa", "xg_chain", "xg_buildup"):
            value = record.stats.get(metric)
            if isinstance(value, (int, float)) and not 0 <= value <= 20:
                findings.append(
                    QualityFinding(
                        rule_key="player_stat.reasonable_advanced_metric",
                        severity=QualitySeverity.ERROR,
                        message=f"{metric} falls outside the accepted per-match range.",
                        source_record_id=record.source_record_id,
                        evidence={"metric": metric, "value": value},
                    )
                )
    return findings


DEFAULT_MATCH_RULES: tuple[MatchQualityRule, ...] = (
    DistinctMatchTeamsRule(),
    DuplicateMatchRule(),
    ScoreConsistencyRule(),
)


def run_match_quality(
    records: list[CanonicalMatchRecord],
    rules: tuple[MatchQualityRule, ...] = DEFAULT_MATCH_RULES,
) -> list[QualityFinding]:
    return [finding for rule in rules for finding in rule.check(records)]
