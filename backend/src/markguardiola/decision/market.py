from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

import numpy as np

from markguardiola.decision.lineup import LineupOptimizer, NoLegalLineupError
from markguardiola.decision.models import (
    LineupDecision,
    MarketCandidate,
    MarketRecommendationResult,
    PlayerDecisionInput,
)
from markguardiola.decision.scenario_search import ScenarioLineupOptimizer
from markguardiola.domain.enums import RiskMode
from markguardiola.fantasy.roster import RosterConstraints, validate_roster
from markguardiola.fantasy.rules import Formation, ScoringRules
from markguardiola.fantasy.rules.models import SubstitutionRules


class MarketOptimizer:
    def __init__(
        self,
        lineup_optimizer: LineupOptimizer | None = None,
        *,
        scoring_rules: ScoringRules | None = None,
        substitution_rules: SubstitutionRules | None = None,
    ) -> None:
        self._lineup_optimizer = lineup_optimizer or LineupOptimizer()
        self._scoring_rules = scoring_rules
        self._substitution_rules = substitution_rules or SubstitutionRules()
        self._evaluated: dict[tuple[tuple[object, ...], ...], LineupDecision] = {}
        self._fixture_inputs: dict[tuple[int, int], PlayerDecisionInput] = {}

    def rank_acquisitions(
        self,
        *,
        roster: list[PlayerDecisionInput],
        candidates: list[MarketCandidate],
        formations: tuple[Formation, ...],
        remaining_budget: float | None,
        recover_purchase_price: bool = False,
        limit: int = 20,
        optimization_horizon: int = 1,
        roster_constraints: RosterConstraints | None = None,
        owned_roles: Mapping[str, tuple[str, ...]] | None = None,
    ) -> tuple[MarketRecommendationResult, ...]:
        self._evaluated.clear()
        self._fixture_inputs.clear()
        complete_roster = (
            dict(owned_roles)
            if owned_roles is not None
            else {player.player_id: player.roles for player in roster}
        )
        if roster_constraints is not None:
            validation = validate_roster(complete_roster, roster_constraints)
            if not validation.valid:
                raise NoLegalLineupError()
        baseline_decisions = self._horizon_decisions(roster, formations, optimization_horizon)
        if baseline_decisions is None:
            raise NoLegalLineupError()
        baseline = baseline_decisions[0]
        baseline_points = sum(decision.expected_points for decision in baseline_decisions)
        baseline_roster = self._horizon_roster(roster, optimization_horizon)
        assert baseline_roster is not None
        horizons = tuple(value for value in (1, 3, 5, 10) if value <= optimization_horizon)
        horizon_baselines = {
            horizon: self._horizon_points(roster, formations, horizon) for horizon in horizons
        }
        baseline_formation_count = self._legal_formation_count(roster, formations)
        owned_ids = {player.player_id for player in roster}
        recommendations: list[MarketRecommendationResult] = []
        for candidate in candidates:
            if not candidate.available or candidate.player.player_id in owned_ids:
                continue
            for drop_index, dropped in enumerate(roster):
                if not set(candidate.player.roles).intersection(dropped.roles):
                    continue
                recovered = dropped.purchase_price or 0.0 if recover_purchase_price else 0.0
                if (
                    candidate.asking_price is not None
                    and remaining_budget is not None
                    and candidate.asking_price > remaining_budget + recovered
                ):
                    continue
                changed = [player for index, player in enumerate(roster) if index != drop_index]
                changed.append(candidate.player)
                if roster_constraints is not None:
                    changed_roles = {
                        player: roles
                        for player, roles in complete_roster.items()
                        if player != dropped.player_id
                    }
                    changed_roles[candidate.player.player_id] = candidate.player.roles
                    if not validate_roster(changed_roles, roster_constraints).valid:
                        continue
                horizon_changed = self._horizon_roster(changed, optimization_horizon)
                if horizon_changed is None:
                    continue
                try:
                    changed_decisions = self._horizon_decisions(
                        changed, formations, optimization_horizon
                    )
                except NoLegalLineupError:
                    continue
                if changed_decisions is None:
                    continue
                optimized = changed_decisions[0]
                improvement = (
                    sum(decision.expected_points for decision in changed_decisions)
                    - baseline_points
                )
                if improvement <= 0:
                    continue
                replacement = _replacement_level(baseline_roster, candidate.player.roles)
                target_points = next(
                    player.expected_points
                    for player in horizon_changed
                    if player.player_id == candidate.player.player_id
                )
                value_over_replacement = target_points - replacement
                horizon_improvements: dict[int, float] = {}
                for horizon in horizons:
                    before = horizon_baselines[horizon]
                    after = self._horizon_points(changed, formations, horizon)
                    if before is not None and after is not None:
                        horizon_improvements[horizon] = after - before
                recommendations.append(
                    MarketRecommendationResult(
                        target_player_id=candidate.player.player_id,
                        target_name=candidate.player.display_name,
                        replace_player_id=dropped.player_id,
                        replace_name=dropped.display_name,
                        price=candidate.asking_price,
                        expected_improvement=improvement,
                        value_over_replacement=value_over_replacement,
                        budget_efficiency=(
                            improvement / candidate.asking_price
                            if candidate.asking_price is not None and candidate.asking_price > 0
                            else None
                        ),
                        formation_before=baseline.formation,
                        formation_after=optimized.formation,
                        horizon_improvements=horizon_improvements,
                        role_flexibility_delta=(
                            self._legal_formation_count(changed, formations)
                            - baseline_formation_count
                        ),
                        affordability="affordable"
                        if candidate.asking_price is not None and remaining_budget is not None
                        else "unknown",
                        optimization_horizon=optimization_horizon,
                        evaluation_method=(
                            "per_fixture_scenario_search"
                            if all(
                                item.optimization_method == "scenario_beam_search"
                                for item in (*baseline_decisions, *changed_decisions)
                            )
                            else "per_fixture_additive_cp_sat"
                        ),
                        formation_schedule_before=tuple(
                            item.formation for item in baseline_decisions
                        ),
                        formation_schedule_after=tuple(
                            item.formation for item in changed_decisions
                        ),
                    )
                )
        recommendations.sort(
            key=lambda item: (
                -item.expected_improvement,
                -item.value_over_replacement,
                item.price if item.price is not None else float("inf"),
                item.target_player_id,
            )
        )
        deduplicated: list[MarketRecommendationResult] = []
        seen_targets: set[str] = set()
        for recommendation in recommendations:
            if recommendation.target_player_id in seen_targets:
                continue
            seen_targets.add(recommendation.target_player_id)
            deduplicated.append(recommendation)
            if len(deduplicated) >= limit:
                break
        return tuple(deduplicated)

    def _horizon_points(
        self,
        roster: list[PlayerDecisionInput],
        formations: tuple[Formation, ...],
        horizon: int,
    ) -> float | None:
        decisions = self._horizon_decisions(roster, formations, horizon)
        if decisions is None:
            return None
        return sum(decision.expected_points for decision in decisions)

    def _horizon_decisions(
        self,
        roster: list[PlayerDecisionInput],
        formations: tuple[Formation, ...],
        horizon: int,
    ) -> tuple[LineupDecision, ...] | None:
        decisions = []
        for offset in range(horizon):
            players = self._fixture_roster(roster, offset)
            if players is None:
                return None
            decisions.append(self._evaluate(players, formations))
        return tuple(decisions)

    def _evaluate(
        self, players: list[PlayerDecisionInput], formations: tuple[Formation, ...]
    ) -> LineupDecision:
        key = tuple(
            sorted(
                (
                    player.player_id,
                    player.expected_points,
                    player.available,
                    id(player.samples),
                    id(player.appearance_samples),
                    id(player.base_rating_samples),
                )
                for player in players
            )
        )
        if key in self._evaluated:
            return self._evaluated[key]
        if self._scoring_rules is not None and all(
            player.appearance_samples is not None and player.samples is not None
            for player in players
        ):
            decision = ScenarioLineupOptimizer(
                self._scoring_rules,
                self._substitution_rules,
                maximum_scenarios=128,
                maximum_candidates=72,
                rounds=2,
            ).optimize(players, formations)
        else:
            decision = self._lineup_optimizer.optimize(
                players,
                formations,
                risk_mode=RiskMode.BALANCED,
                bench_size=self._substitution_rules.bench_size,
            )
        self._evaluated[key] = decision
        return decision

    def _horizon_roster(
        self, roster: list[PlayerDecisionInput], horizon: int
    ) -> list[PlayerDecisionInput] | None:

        if horizon == 1:
            return roster
        periods = [self._fixture_roster(roster, offset) for offset in range(horizon)]
        if any(period is None for period in periods):
            return None
        return [
            replace(
                player,
                expected_points=sum(
                    period[index].expected_points for period in periods if period is not None
                ),
                samples=None,
                appearance_samples=None,
                base_rating_samples=None,
            )
            for index, player in enumerate(roster)
        ]

    def _fixture_roster(
        self, roster: list[PlayerDecisionInput], offset: int
    ) -> list[PlayerDecisionInput] | None:
        if offset == 0:
            return roster
        if any(len(player.fixture_projections) <= offset for player in roster):
            return None
        output = []
        for player in roster:
            key = (id(player), offset)
            if key in self._fixture_inputs:
                output.append(self._fixture_inputs[key])
                continue
            projection = player.fixture_projections[offset]
            self._fixture_inputs[key] = replace(
                player,
                expected_points=float(np.mean(projection.samples)),
                median_points=float(np.median(projection.samples)),
                p10_points=float(np.quantile(projection.samples, 0.1)),
                p90_points=float(np.quantile(projection.samples, 0.9)),
                appearance_probability=float(np.mean(projection.appearance_samples)),
                available=projection.available,
                samples=projection.samples,
                appearance_samples=projection.appearance_samples,
                base_rating_samples=projection.base_rating_samples,
            )
            output.append(self._fixture_inputs[key])
        return output

    def _legal_formation_count(
        self,
        roster: list[PlayerDecisionInput],
        formations: tuple[Formation, ...],
    ) -> int:
        count = 0
        for formation in formations:
            try:
                self._lineup_optimizer.optimize(roster, (formation,))
            except NoLegalLineupError:
                continue
            count += 1
        return count


def _replacement_level(roster: list[PlayerDecisionInput], roles: tuple[str, ...]) -> float:
    compatible = [
        player.expected_points for player in roster if set(player.roles).intersection(roles)
    ]
    return min(compatible) if compatible else 0.0
