from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from functools import lru_cache

import numpy as np
from numpy.typing import NDArray

from markguardiola.decision.models import LineupDecision, PlayerDecisionInput
from markguardiola.fantasy.rules import Formation, ScoringRules
from markguardiola.fantasy.rules.models import SubstitutionRules


@dataclass(frozen=True, slots=True)
class LineupScores:
    scores: NDArray[np.float64]
    substitution_counts: NDArray[np.int64]
    modifier_scores: NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class LineupScoringContext:
    points: NDArray[np.float64]
    ratings: NDArray[np.float64]
    full_appearances: NDArray[np.bool_]

    @classmethod
    def build(cls, players: list[PlayerDecisionInput]) -> LineupScoringContext:
        if not players or any(
            player.samples is None or player.appearance_samples is None for player in players
        ):
            raise ValueError()
        points = np.stack(
            [player.samples for player in players if player.samples is not None]
        ).astype(float)
        appearances = np.stack(
            [
                player.appearance_samples
                for player in players
                if player.appearance_samples is not None
            ]
        ).astype(bool)
        if points.shape != appearances.shape or not np.all(np.isfinite(points)):
            raise ValueError()
        count = points.shape[1]
        ratings = np.stack(
            [
                player.base_rating_samples
                if player.base_rating_samples is not None
                else np.full(count, np.nan)
                for player in players
            ]
        ).astype(float)
        return cls(points, ratings, appearances)


def score_lineup(
    decision: LineupDecision,
    players: list[PlayerDecisionInput],
    formations: tuple[Formation, ...],
    scoring: ScoringRules,
    substitutions: SubstitutionRules,
    *,
    context: LineupScoringContext | None = None,
) -> LineupScores:
    context = context or LineupScoringContext.build(players)
    index = {player.player_id: number for number, player in enumerate(players)}
    starters = [index[player.player_id] for player in decision.starters]
    bench = [index[player.player_id] for player in decision.bench]
    configured = tuple(item for item in formations if item.name == decision.formation)
    if not configured:
        raise ValueError()
    allowed = formations if substitutions.allow_formation_change else configured
    if all(len(player.roles) == 1 for player in players) and len(bench) < 63:
        return _single_role_scores(
            decision, players, starters, bench, allowed, scoring, substitutions, context
        )
    return _multirole_scores(players, starters, bench, allowed, scoring, substitutions, context)


def _multirole_scores(
    players: list[PlayerDecisionInput],
    starters: list[int],
    bench: list[int],
    formations: tuple[Formation, ...],
    scoring: ScoringRules,
    substitutions: SubstitutionRules,
    context: LineupScoringContext,
) -> LineupScores:

    roles = [tuple(sorted(set(player.roles))) for player in players]
    groups: dict[tuple[str, ...], list[int]] = {}
    for number in starters:
        groups.setdefault(roles[number], []).append(number)
    role_groups = sorted(groups)
    signature = np.stack(
        [context.full_appearances[groups[role]].sum(axis=0) for role in role_groups]
        + [context.full_appearances[number] for number in bench],
        axis=1,
    )
    patterns, inverse = _group_role_patterns(signature)
    active_patterns, active_inverse = _group_role_patterns(patterns[:, : len(role_groups)])
    bench_patterns, bench_inverse = _group_role_patterns(patterns[:, len(role_groups) :])
    formation_slots = tuple(formation.slots for formation in formations)
    active_keys = [
        tuple(
            role
            for role, count in zip(role_groups, pattern, strict=True)
            for _ in range(int(count))
        )
        for pattern in active_patterns
    ]
    bench_keys = [
        tuple(
            roles[number] if appeared else ()
            for number, appeared in zip(bench, pattern, strict=True)
        )
        for pattern in bench_patterns
    ]

    bench_selections = np.asarray(
        [
            _role_substitutions(
                active_keys[active_index],
                bench_keys[bench_index],
                formation_slots,
                substitutions.maximum_substitutions,
            )
            for active_index, bench_index in zip(active_inverse, bench_inverse, strict=True)
        ],
        dtype=bool,
    ).reshape(len(patterns), len(bench))
    selected = np.zeros_like(context.full_appearances)
    selected[starters] = context.full_appearances[starters]
    selected[bench] = bench_selections[inverse].T
    order = starters + bench
    scores = np.where(selected[order], context.points[order], 0).sum(axis=0)
    changes = selected[bench].sum(axis=0, dtype=np.int64)
    modifiers = np.zeros(context.points.shape[1], dtype=float)
    if scoring.defensive_modifier_enabled:
        eligible = [
            number
            for number in order
            if players[number].scoring_role in scoring.defensive_modifier_roles
        ]
        for number in eligible:
            if players[number].base_rating_samples is None and np.any(selected[number]):
                raise ValueError()
        if eligible:
            active_ratings = selected[eligible]
            count = active_ratings.sum(axis=0)
            average = np.where(active_ratings, context.ratings[eligible], 0).sum(
                axis=0
            ) / np.maximum(count, 1)
            for band in scoring.defensive_modifier_bands:
                modifiers = np.where(
                    (count > 0) & (average >= band.minimum_average), band.points, modifiers
                )
    return LineupScores(scores + modifiers, changes, modifiers)


def _group_role_patterns(
    signature: NDArray[np.int64] | NDArray[np.uint8],
) -> tuple[NDArray[np.uint8], NDArray[np.intp]]:

    rows = np.ascontiguousarray(signature, dtype=np.uint8)
    width = rows.shape[1]
    if width == 0:
        return np.empty((1, 0), dtype=np.uint8), np.zeros(len(rows), dtype=np.intp)
    keys = rows.view(np.dtype((np.void, width))).ravel()
    patterns, inverse = np.unique(keys, return_inverse=True)
    return patterns.view(np.uint8).reshape(-1, width), inverse


@lru_cache(maxsize=32_768)
def _role_substitutions(
    active_roles: tuple[tuple[str, ...], ...],
    bench_roles: tuple[tuple[str, ...], ...],
    formations: tuple[tuple[str, ...], ...],
    maximum: int,
) -> tuple[bool, ...]:

    roles = active_roles + bench_roles
    alternatives: list[tuple[int, ...]] = []
    for slots in formations:
        assigned: dict[int, int] = {}
        if not all(
            _assign_roles(number, roles, slots, assigned, set())
            for number in range(len(active_roles))
        ):
            continue
        added: list[int] = []
        for position, eligibility in enumerate(bench_roles):
            if len(added) >= maximum:
                break
            if eligibility and _assign_roles(
                len(active_roles) + position, roles, slots, assigned, set()
            ):
                added.append(position)
        alternatives.append(tuple(added))
    if not alternatives:
        raise ValueError()

    chosen = min(alternatives, key=lambda additions: (-len(additions), additions))
    return tuple(position in chosen for position in range(len(bench_roles)))


def _single_role_scores(
    decision: LineupDecision,
    players: list[PlayerDecisionInput],
    starters: list[int],
    bench: list[int],
    formations: tuple[Formation, ...],
    scoring: ScoringRules,
    substitutions: SubstitutionRules,
    context: LineupScoringContext,
) -> LineupScores:

    count = context.points.shape[1]
    active = np.zeros_like(context.full_appearances)
    active[starters] = context.full_appearances[starters]
    roles = sorted({player.roles[0] for player in players})
    active_counts = {
        role: active[[i for i, p in enumerate(players) if p.roles[0] == role]].sum(axis=0)
        for role in roles
    }
    best_scores = np.zeros(count)
    best_changes = np.zeros(count, dtype=np.int64)
    best_modifiers = np.zeros(count)
    best_priority = np.zeros(count, dtype=np.int64)
    chosen = np.zeros(count, dtype=bool)
    eligible_ratings = [
        i for i, p in enumerate(players) if p.scoring_role in scoring.defensive_modifier_roles
    ]
    for formation in sorted(
        formations, key=lambda item: (item.name != decision.formation, item.name)
    ):
        capacity = Counter(formation.slots)
        feasible = np.ones(count, dtype=bool)
        used = {role: values.copy() for role, values in active_counts.items()}
        for role in roles:
            feasible &= used[role] <= capacity[role]
        selected = active.copy()
        changes = np.zeros(count, dtype=np.int64)
        priority = np.zeros(count, dtype=np.int64)
        for order, number in enumerate(bench):
            role = players[number].roles[0]
            enters = (
                context.full_appearances[number]
                & (used[role] < capacity[role])
                & (changes < substitutions.maximum_substitutions)
            )
            selected[number] = enters
            used[role] += enters
            changes += enters
            priority += enters.astype(np.int64) * (1 << (len(bench) - order - 1))
        scores = np.where(selected, context.points, 0).sum(axis=0)
        modifiers = np.zeros(count)
        if scoring.defensive_modifier_enabled and eligible_ratings:
            for number in eligible_ratings:
                if players[number].base_rating_samples is None and np.any(
                    selected[number] & feasible
                ):
                    raise ValueError()
            selected_ratings = selected[eligible_ratings]
            denominator = selected_ratings.sum(axis=0)
            average = np.where(selected_ratings, context.ratings[eligible_ratings], 0).sum(
                axis=0
            ) / np.maximum(denominator, 1)
            for band in scoring.defensive_modifier_bands:
                modifiers = np.where(
                    (denominator > 0) & (average >= band.minimum_average), band.points, modifiers
                )
        take = feasible & (
            ~chosen
            | (changes > best_changes)
            | ((changes == best_changes) & (priority > best_priority))
        )
        best_scores[take] = scores[take] + modifiers[take]
        best_changes[take] = changes[take]
        best_modifiers[take] = modifiers[take]
        best_priority[take] = priority[take]
        chosen |= feasible
    if not np.all(chosen):
        raise ValueError()
    return LineupScores(best_scores, best_changes, best_modifiers)


def apply_lineup_scoring(
    decision: LineupDecision,
    players: list[PlayerDecisionInput],
    formations: tuple[Formation, ...],
    scoring: ScoringRules,
    substitutions: SubstitutionRules,
    *,
    context: LineupScoringContext | None = None,
) -> LineupDecision:
    if substitutions.bench_size is not None:
        decision = replace(decision, bench=decision.bench[: substitutions.bench_size])
    result = score_lineup(decision, players, formations, scoring, substitutions, context=context)
    return replace(
        decision,
        expected_points=float(result.scores.mean()),
        p10_points=float(np.quantile(result.scores, 0.1)),
        p90_points=float(np.quantile(result.scores, 0.9)),
        score_samples=result.scores,
        expected_substitutions=float(result.substitution_counts.mean()),
        expected_modifier=float(result.modifier_scores.mean()),
    )


def _assign(
    player_index: int,
    players: list[PlayerDecisionInput],
    slots: tuple[str, ...],
    assigned: dict[int, int],
    visited: set[int],
) -> bool:

    return _assign_roles(
        player_index, tuple(player.roles for player in players), slots, assigned, visited
    )


def _assign_roles(
    player_index: int,
    roles: tuple[tuple[str, ...], ...],
    slots: tuple[str, ...],
    assigned: dict[int, int],
    visited: set[int],
) -> bool:
    for slot_index, role in enumerate(slots):
        if slot_index in visited or role not in roles[player_index]:
            continue
        visited.add(slot_index)
        existing = assigned.get(slot_index)
        if existing is None or _assign_roles(existing, roles, slots, assigned, visited):
            assigned[slot_index] = player_index
            return True
    return False
