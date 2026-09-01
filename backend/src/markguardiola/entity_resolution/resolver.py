from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from rapidfuzz.fuzz import WRatio

from markguardiola.domain.enums import ResolutionMethod
from markguardiola.entity_resolution.normalization import normalize_name


class ResolutionStatus(StrEnum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class IdentityQuery:
    name: str
    provider_entity_id: str | None = None
    date_of_birth: date | None = None
    nationality_code: str | None = None
    team_id: uuid.UUID | None = None
    position: str | None = None
    context_date: date | None = None


@dataclass(frozen=True, slots=True)
class IdentityCandidate:
    canonical_id: uuid.UUID
    name: str
    date_of_birth: date | None = None
    nationality_code: str | None = None
    team_id: uuid.UUID | None = None
    position: str | None = None
    team_valid_from: date | None = None
    team_valid_to: date | None = None


@dataclass(frozen=True, slots=True)
class ScoredCandidate:
    candidate: IdentityCandidate
    confidence: float
    evidence: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ResolutionResult:
    status: ResolutionStatus
    selected: IdentityCandidate | None
    confidence: float
    method: ResolutionMethod | None
    candidates: tuple[ScoredCandidate, ...]


class EntityResolver:
    def __init__(
        self,
        *,
        automatic_threshold: float = 0.87,
        review_threshold: float = 0.70,
        ambiguity_margin: float = 0.04,
    ) -> None:
        if not 0 <= review_threshold <= automatic_threshold <= 1:
            raise ValueError()
        self._automatic_threshold = automatic_threshold
        self._review_threshold = review_threshold
        self._ambiguity_margin = ambiguity_margin

    def resolve(
        self,
        query: IdentityQuery,
        candidates: list[IdentityCandidate],
        *,
        existing_mapping: uuid.UUID | None = None,
    ) -> ResolutionResult:
        if existing_mapping is not None:
            mapped = next(
                (
                    candidate
                    for candidate in candidates
                    if candidate.canonical_id == existing_mapping
                ),
                None,
            )
            if mapped is not None:
                mapped_scored = ScoredCandidate(mapped, 1.0, ("existing_provider_mapping",))
                return ResolutionResult(
                    status=ResolutionStatus.RESOLVED,
                    selected=mapped,
                    confidence=1.0,
                    method=ResolutionMethod.EXISTING_MAPPING,
                    candidates=(mapped_scored,),
                )

        scored = tuple(
            sorted(
                (self._score(query, candidate) for candidate in candidates),
                key=lambda item: (-item.confidence, str(item.candidate.canonical_id)),
            )
        )
        if not scored or scored[0].confidence < self._review_threshold:
            return ResolutionResult(
                status=ResolutionStatus.UNRESOLVED,
                selected=None,
                confidence=scored[0].confidence if scored else 0.0,
                method=None,
                candidates=scored[:5],
            )

        leader = scored[0]
        close_second = (
            len(scored) > 1 and leader.confidence - scored[1].confidence <= self._ambiguity_margin
        )
        if leader.confidence < self._automatic_threshold or close_second:
            return ResolutionResult(
                status=ResolutionStatus.AMBIGUOUS,
                selected=None,
                confidence=leader.confidence,
                method=None,
                candidates=scored[:5],
            )

        method = (
            ResolutionMethod.EXACT
            if normalize_name(query.name) == normalize_name(leader.candidate.name)
            else ResolutionMethod.FUZZY
        )
        if "temporal_team_match" in leader.evidence:
            method = ResolutionMethod.TEMPORAL_CONTEXT
        return ResolutionResult(
            status=ResolutionStatus.RESOLVED,
            selected=leader.candidate,
            confidence=leader.confidence,
            method=method,
            candidates=scored[:5],
        )

    def _score(self, query: IdentityQuery, candidate: IdentityCandidate) -> ScoredCandidate:
        query_name = normalize_name(query.name)
        candidate_name = normalize_name(candidate.name)
        name_ratio = WRatio(query_name, candidate_name) / 100.0
        confidence = 0.82 if query_name == candidate_name else 0.70 * name_ratio
        evidence = ["exact_normalized_name" if query_name == candidate_name else "fuzzy_name"]

        if query.date_of_birth is not None and candidate.date_of_birth is not None:
            if query.date_of_birth == candidate.date_of_birth:
                confidence += 0.14
                evidence.append("date_of_birth_match")
            else:
                confidence -= 0.30
                evidence.append("date_of_birth_conflict")

        if query.nationality_code and candidate.nationality_code:
            if query.nationality_code.casefold() == candidate.nationality_code.casefold():
                confidence += 0.03
                evidence.append("nationality_match")
            else:
                confidence -= 0.02

        if query.team_id is not None and candidate.team_id is not None:
            team_matches = query.team_id == candidate.team_id
            within_period = query.context_date is None or (
                (
                    candidate.team_valid_from is None
                    or candidate.team_valid_from <= query.context_date
                )
                and (
                    candidate.team_valid_to is None or candidate.team_valid_to >= query.context_date
                )
            )
            if team_matches and within_period:
                confidence += 0.08
                evidence.append("temporal_team_match")
            elif not team_matches:
                confidence -= 0.05

        if (
            query.position
            and candidate.position
            and normalize_name(query.position) == normalize_name(candidate.position)
        ):
            confidence += 0.02
            evidence.append("position_match")

        return ScoredCandidate(
            candidate=candidate,
            confidence=round(max(0.0, min(confidence, 1.0)), 6),
            evidence=tuple(evidence),
        )
