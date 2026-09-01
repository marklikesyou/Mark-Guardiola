from __future__ import annotations

from collections import defaultdict
from dataclasses import replace

import numpy as np

from markguardiola.decision import LineupOptimizer, MarketCandidate, MarketOptimizer
from markguardiola.decision.lineup_scoring import apply_lineup_scoring
from markguardiola.decision.models import LineupDecision, PlayerDecisionInput
from markguardiola.decision.scenario_search import ScenarioLineupOptimizer
from markguardiola.domain.enums import RiskMode
from markguardiola.fantasy.rules import CLASSIC_FORMATIONS, ScoringRules
from markguardiola.fantasy.rules.models import SubstitutionRules


def draft_benchmark_rosters(
    players: list[PlayerDecisionInput], minutes: dict[str, float], *, seed: int
) -> tuple[list[PlayerDecisionInput], list[PlayerDecisionInput], list[MarketCandidate]]:

    by_role: dict[str, list[PlayerDecisionInput]] = defaultdict(list)
    for player in players:
        if player.available:
            by_role[player.roles[0]].append(player)
    random = np.random.default_rng(seed)
    first: list[PlayerDecisionInput] = []
    second: list[PlayerDecisionInput] = []
    market: list[MarketCandidate] = []
    for role, size in (("GK", 3), ("DEF", 8), ("MID", 8), ("FWD", 6)):
        ranked = sorted(by_role[role], key=lambda p: (-minutes.get(p.player_id, 0), p.player_id))
        if len(ranked) < 2 * size + 1:
            raise ValueError()
        pool = ranked[: min(len(ranked), 4 * size + 1)]
        order = random.permutation(len(pool))
        first.extend(pool[index] for index in order[:size])
        second.extend(pool[index] for index in order[size : 2 * size])
        market.append(MarketCandidate(pool[order[2 * size]], asking_price=None))
    return first, second, market


def evaluate_decision_case(
    roster: list[PlayerDecisionInput],
    opponent: list[PlayerDecisionInput],
    market: list[MarketCandidate],
    *,
    past_minutes: dict[str, float],
    observed: dict[str, tuple[float, bool]],
    scoring: ScoringRules,
    substitutions: SubstitutionRules,
) -> dict[str, object]:

    optimizer = ScenarioLineupOptimizer(scoring, substitutions)
    balanced = optimizer.optimize(roster, CLASSIC_FORMATIONS)
    opponent_decision = optimizer.optimize(opponent, CLASSIC_FORMATIONS)
    matchup = optimizer.optimize(
        roster,
        CLASSIC_FORMATIONS,
        risk_mode=RiskMode.MATCHUP,
        opponent_samples=opponent_decision.score_samples,
        initial=balanced,
    )
    naive = LineupOptimizer().optimize(
        [
            replace(
                player,
                expected_points=past_minutes.get(player.player_id, 0),
                appearance_probability=min(1.0, past_minutes.get(player.player_id, 0) / 270),
            )
            for player in roster
        ],
        CLASSIC_FORMATIONS,
        bench_size=substitutions.bench_size,
    )
    naive = apply_lineup_scoring(naive, roster, CLASSIC_FORMATIONS, scoring, substitutions)
    acquisitions = MarketOptimizer(
        scoring_rules=scoring, substitution_rules=substitutions
    ).rank_acquisitions(
        roster=roster,
        candidates=market,
        formations=CLASSIC_FORMATIONS,
        remaining_budget=None,
        limit=1,
    )

    def actual_inputs(players: list[PlayerDecisionInput]) -> list[PlayerDecisionInput]:
        output = []
        for player in players:
            points, appeared = observed[player.player_id]
            output.append(
                replace(
                    player,
                    expected_points=points,
                    median_points=points,
                    p10_points=points,
                    p90_points=points,
                    appearance_probability=float(appeared),
                    available=True,
                    samples=np.array([points]),
                    appearance_samples=np.array([appeared]),
                    base_rating_samples=np.array([scoring.base_rating_fallback]),
                )
            )
        return output

    actual_roster = actual_inputs(roster)

    def score(decision: LineupDecision, players: list[PlayerDecisionInput]) -> float:
        return apply_lineup_scoring(
            decision, players, CLASSIC_FORMATIONS, scoring, substitutions
        ).expected_points

    actual_balanced, actual_naive, actual_matchup = (
        score(decision, actual_roster) for decision in (balanced, naive, matchup)
    )
    actual_opponent = score(opponent_decision, actual_inputs(opponent))
    hindsight = optimizer.optimize(actual_roster, CLASSIC_FORMATIONS, initial=balanced)
    best_known = max(hindsight.expected_points, actual_balanced, actual_naive, actual_matchup)
    market_result: dict[str, object] | None = None
    if acquisitions:
        acquisition = acquisitions[0]
        target = next(
            item.player for item in market if item.player.player_id == acquisition.target_player_id
        )
        changed = [
            player for player in roster if player.player_id != acquisition.replace_player_id
        ] + [target]
        market_policy = ScenarioLineupOptimizer(
            scoring, substitutions, maximum_scenarios=128, maximum_candidates=72, rounds=2
        )
        before = market_policy.optimize(roster, CLASSIC_FORMATIONS)
        after = market_policy.optimize(changed, CLASSIC_FORMATIONS)
        market_result = {
            "target_player_id": target.player_id,
            "replace_player_id": acquisition.replace_player_id,
            "predicted_lift": acquisition.expected_improvement,
            "observed_lift": score(after, actual_inputs(changed)) - score(before, actual_roster),
            "price": None,
            "affordability": "unknown",
        }

    def wins(decision: LineupDecision) -> float:
        assert decision.score_samples is not None and opponent_decision.score_samples is not None
        return float(np.mean(decision.score_samples > opponent_decision.score_samples + 1e-8))

    return {
        "roster_player_ids": [player.player_id for player in roster],
        "opponent_player_ids": [player.player_id for player in opponent],
        "balanced_starters": [player.player_id for player in balanced.starters],
        "balanced_bench": [player.player_id for player in balanced.bench],
        "naive_starters": [player.player_id for player in naive.starters],
        "matchup_starters": [player.player_id for player in matchup.starters],
        "observed_balanced_score": actual_balanced,
        "observed_naive_score": actual_naive,
        "observed_matchup_score": actual_matchup,
        "observed_opponent_score": actual_opponent,
        "observed_lineup_lift": actual_balanced - actual_naive,
        "best_known_hindsight_score": best_known,
        "hindsight_global_optimality_proven": False,
        "regret_to_best_known": best_known - actual_balanced,
        "predicted_balanced_win_probability": wins(balanced),
        "predicted_matchup_win_probability": wins(matchup),
        "observed_balanced_win": float(actual_balanced > actual_opponent + 1e-8),
        "observed_naive_win": float(actual_naive > actual_opponent + 1e-8),
        "observed_matchup_win": float(actual_matchup > actual_opponent + 1e-8),
        "market": market_result,
    }
