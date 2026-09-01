from collections.abc import Iterator
from dataclasses import replace

import numpy as np
from numpy.typing import NDArray

from markguardiola.decision.lineup import LineupOptimizer, NoLegalLineupError, order_bench
from markguardiola.decision.lineup_scoring import (
    LineupScoringContext,
    _assign,
    apply_lineup_scoring,
)
from markguardiola.decision.models import (
    BenchPlayer,
    LineupDecision,
    PlayerDecisionInput,
    SelectedPlayer,
)
from markguardiola.domain.enums import RiskMode
from markguardiola.fantasy.rules import Formation, ScoringRules
from markguardiola.fantasy.rules.models import SubstitutionRules


class ScenarioLineupOptimizer:
    def __init__(
        self,
        scoring: ScoringRules,
        substitutions: SubstitutionRules,
        *,
        maximum_scenarios: int = 256,
        maximum_candidates: int = 240,
        beam_width: int = 3,
        rounds: int = 3,
    ) -> None:
        if min(maximum_scenarios, maximum_candidates, beam_width, rounds) < 1:
            raise ValueError()
        self.scoring = scoring
        self.substitutions = substitutions
        self.maximum_scenarios = maximum_scenarios
        self.maximum_candidates = maximum_candidates
        self.beam_width = beam_width
        self.rounds = rounds

    def optimize(
        self,
        players: list[PlayerDecisionInput],
        formations: tuple[Formation, ...],
        *,
        risk_mode: RiskMode = RiskMode.BALANCED,
        bench_size: int | None = None,
        opponent_samples: NDArray[np.float64] | None = None,
        initial: LineupDecision | None = None,
    ) -> LineupDecision:
        if risk_mode == RiskMode.MATCHUP and opponent_samples is None:
            raise ValueError()
        players = sorted(players, key=lambda player: player.player_id)
        full_context = LineupScoringContext.build(players)
        count = full_context.points.shape[1]
        if opponent_samples is not None and opponent_samples.shape != (count,):
            raise ValueError()
        limits = [
            value for value in (bench_size, self.substitutions.bench_size) if value is not None
        ]
        bench_limit = min(limits) if limits else None
        indices = np.linspace(0, count - 1, min(count, self.maximum_scenarios), dtype=int)
        search_players = [
            replace(
                player,
                samples=player.samples[indices] if player.samples is not None else None,
                appearance_samples=player.appearance_samples[indices]
                if player.appearance_samples is not None
                else None,
                base_rating_samples=player.base_rating_samples[indices]
                if player.base_rating_samples is not None
                else None,
            )
            for player in players
        ]
        context = LineupScoringContext.build(search_players)
        search_opponent = opponent_samples[indices] if opponent_samples is not None else None
        seeds: dict[tuple[object, ...], LineupDecision] = {}
        if initial is not None:
            initial = replace(initial, bench=initial.bench[:bench_limit])
            seeds[_key(initial)] = initial
        for formation in formations:
            try:
                seed = LineupOptimizer().optimize(
                    players,
                    (formation,),
                    risk_mode=risk_mode if risk_mode != RiskMode.MATCHUP else RiskMode.BALANCED,
                    bench_size=bench_limit,
                )
            except NoLegalLineupError:
                continue
            seeds[_key(seed)] = seed
        if not seeds:
            raise NoLegalLineupError()
        evaluated: dict[tuple[object, ...], LineupDecision] = {}

        def evaluate(candidate: LineupDecision) -> None:
            key = _key(candidate)
            if key in evaluated:
                return
            scored = apply_lineup_scoring(
                candidate,
                search_players,
                formations,
                self.scoring,
                self.substitutions,
                context=context,
            )
            evaluated[key] = scored

        def rank(candidate: LineupDecision) -> tuple[float, float, float]:
            return _utility(candidate, risk_mode, search_opponent)

        for seed in seeds.values():
            evaluate(seed)
        for _ in range(self.rounds):
            leaders = sorted(evaluated.values(), key=rank, reverse=True)[: self.beam_width]
            previous = set(evaluated)

            streams = [
                iter(_neighbours(leader, players, formations, bench_limit)) for leader in leaders
            ]
            round_budget = min(
                self.maximum_candidates,
                len(evaluated) + max(1, self.maximum_candidates // self.rounds),
            )
            while streams and len(evaluated) < round_budget:
                remaining = []
                for stream in streams:
                    candidate = next(stream, None)
                    if candidate is not None:
                        evaluate(candidate)
                        remaining.append(stream)
                    if len(evaluated) >= round_budget:
                        break
                streams = remaining
            if set(evaluated) == previous or len(evaluated) >= self.maximum_candidates:
                break
        finalists = dict(seeds)
        finalists.update(
            {_key(item): item for item in sorted(evaluated.values(), key=rank, reverse=True)[:12]}
        )
        full = [
            apply_lineup_scoring(
                candidate,
                players,
                formations,
                self.scoring,
                self.substitutions,
                context=full_context,
            )
            for candidate in finalists.values()
        ]
        best = max(full, key=lambda candidate: _utility(candidate, risk_mode, opponent_samples))
        return replace(
            best,
            risk_mode=risk_mode,
            objective_value=_utility(best, risk_mode, opponent_samples)[0],
            optimization_method="scenario_beam_search",
            evaluated_candidates=len(evaluated),
            search_scenarios=len(indices),
        )


def _key(decision: LineupDecision) -> tuple[object, ...]:
    return (
        decision.formation,
        tuple(sorted(item.player_id for item in decision.starters)),
        tuple(item.player_id for item in decision.bench),
    )


def _utility(
    decision: LineupDecision,
    risk_mode: RiskMode,
    opponent: NDArray[np.float64] | None,
) -> tuple[float, float, float]:
    if opponent is not None:
        assert decision.score_samples is not None
        difference = decision.score_samples - opponent
        draw = np.isclose(difference, 0, atol=1e-8, rtol=0)
        return (
            float(np.mean((difference > 0) & ~draw)),
            float(np.mean(draw)),
            decision.expected_points,
        )
    if risk_mode == RiskMode.FLOOR:
        value = 0.6 * decision.expected_points + 0.4 * decision.p10_points
    elif risk_mode == RiskMode.UPSIDE:
        value = 0.6 * decision.expected_points + 0.4 * decision.p90_points
    else:
        value = decision.expected_points
    return value, decision.expected_points, decision.p10_points


def _neighbours(
    decision: LineupDecision,
    players: list[PlayerDecisionInput],
    formations: tuple[Formation, ...],
    bench_limit: int | None,
) -> Iterator[LineupDecision]:
    index = {player.player_id: number for number, player in enumerate(players)}
    starter_indices = {index[player.player_id] for player in decision.starters}
    formation = next(item for item in formations if item.name == decision.formation)
    reserves = [
        number
        for number, player in enumerate(players)
        if number not in starter_indices and player.available
    ]
    for incoming in reserves:
        for outgoing in sorted(starter_indices):
            changed = starter_indices - {outgoing} | {incoming}
            assigned: dict[int, int] = {}
            if not all(
                _assign(number, players, formation.slots, assigned, set())
                for number in sorted(changed)
            ):
                continue
            starters = [
                SelectedPlayer(
                    players[number].player_id,
                    players[number].display_name,
                    formation.slots[slot],
                    players[number].expected_points,
                    players[number].appearance_probability,
                )
                for slot, number in sorted(assigned.items())
            ]
            yield replace(
                decision,
                starters=tuple(starters),
                bench=order_bench(
                    players,
                    changed,
                    starters,
                    limit=bench_limit,
                ),
            )
    bench = decision.bench
    for left in range(len(bench)):
        for right in range(left + 1, len(bench)):
            changed_bench = list(bench)
            changed_bench[left], changed_bench[right] = changed_bench[right], changed_bench[left]
            yield replace(decision, bench=tuple(changed_bench))
        bench_ids = {item.player_id for item in bench}
        for number in reserves:
            player = players[number]
            if player.player_id in bench_ids:
                continue
            changed_bench = list(bench)
            changed_bench[left] = BenchPlayer(
                player.player_id, player.display_name, player.roles, player.expected_points
            )
            yield replace(decision, bench=tuple(changed_bench))
