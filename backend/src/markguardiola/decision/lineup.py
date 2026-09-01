from __future__ import annotations

from collections import defaultdict

import numpy as np
from ortools.sat.python import cp_model

from markguardiola.decision.models import (
    BenchPlayer,
    LineupDecision,
    PlayerDecisionInput,
    SelectedPlayer,
)
from markguardiola.domain.enums import RiskMode
from markguardiola.fantasy.rules import Formation


class NoLegalLineupError(ValueError):
    pass


class LineupOptimizer:
    def __init__(self, *, time_limit_seconds: float = 10.0) -> None:
        self._time_limit_seconds = time_limit_seconds

    def optimize(
        self,
        players: list[PlayerDecisionInput],
        formations: tuple[Formation, ...],
        *,
        risk_mode: RiskMode = RiskMode.BALANCED,
        bench_size: int | None = None,
    ) -> LineupDecision:
        if not formations:
            raise NoLegalLineupError()
        if len({player.player_id for player in players}) != len(players):
            raise ValueError()
        model = cp_model.CpModel()
        formation_selected = [
            model.new_bool_var(f"formation_{index}") for index in range(len(formations))
        ]
        model.add_exactly_one(formation_selected)
        assignments: dict[tuple[int, int, int], cp_model.IntVar] = {}
        by_player: dict[int, list[cp_model.IntVar]] = defaultdict(list)
        for formation_index, formation in enumerate(formations):
            for slot_index, slot in enumerate(formation.slots):
                slot_variables: list[cp_model.IntVar] = []
                for player_index, player in enumerate(players):
                    if not player.available or slot not in player.roles:
                        continue
                    variable = model.new_bool_var(
                        f"assign_{formation_index}_{slot_index}_{player_index}"
                    )
                    assignments[(formation_index, slot_index, player_index)] = variable
                    slot_variables.append(variable)
                    by_player[player_index].append(variable)
                if not slot_variables:
                    model.add(formation_selected[formation_index] == 0)
                else:
                    model.add(sum(slot_variables) == formation_selected[formation_index])
        for variables in by_player.values():
            model.add(sum(variables) <= 1)

        scale = 10_000
        model.maximize(
            sum(
                round(_objective(players[player_index], risk_mode) * scale) * variable
                for (formation_index, slot_index, player_index), variable in assignments.items()
            )
        )
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = self._time_limit_seconds
        solver.parameters.num_search_workers = 1
        solver.parameters.random_seed = 2026
        status = solver.solve(model)
        if status not in {cp_model.OPTIMAL, cp_model.FEASIBLE}:
            raise NoLegalLineupError()

        chosen_formation_index = next(
            index
            for index, variable in enumerate(formation_selected)
            if solver.boolean_value(variable)
        )
        chosen_formation = formations[chosen_formation_index]
        starters: list[SelectedPlayer] = []
        starter_indices: set[int] = set()
        for (formation_index, slot_index, player_index), variable in assignments.items():
            if formation_index != chosen_formation_index or not solver.boolean_value(variable):
                continue
            player = players[player_index]
            starter_indices.add(player_index)
            starters.append(
                SelectedPlayer(
                    player_id=player.player_id,
                    display_name=player.display_name,
                    slot=chosen_formation.slots[slot_index],
                    expected_points=player.expected_points,
                    appearance_probability=player.appearance_probability,
                )
            )

        starters.sort(key=lambda item: (chosen_formation.slots.index(item.slot), item.player_id))
        bench = order_bench(
            players,
            starter_indices,
            starters,
            limit=bench_size,
        )
        selected_samples = [players[index].samples for index in starter_indices]
        joint_samples = (
            np.sum(np.stack([sample for sample in selected_samples if sample is not None]), axis=0)
            if all(sample is not None for sample in selected_samples)
            else None
        )
        return LineupDecision(
            formation=chosen_formation.name,
            risk_mode=risk_mode,
            starters=tuple(starters),
            bench=bench,
            objective_value=sum(_objective(players[index], risk_mode) for index in starter_indices),
            expected_points=sum(players[index].expected_points for index in starter_indices),
            p10_points=float(np.quantile(joint_samples, 0.1))
            if joint_samples is not None
            else sum(players[index].p10_points for index in starter_indices),
            p90_points=float(np.quantile(joint_samples, 0.9))
            if joint_samples is not None
            else sum(players[index].p90_points for index in starter_indices),
        )


def _objective(player: PlayerDecisionInput, risk_mode: RiskMode) -> float:
    if risk_mode == RiskMode.FLOOR:
        return 0.6 * player.expected_points + 0.4 * player.p10_points
    if risk_mode == RiskMode.UPSIDE:
        return 0.6 * player.expected_points + 0.4 * player.p90_points
    return player.expected_points


def order_bench(
    players: list[PlayerDecisionInput],
    starter_indices: set[int],
    starters: list[SelectedPlayer],
    *,
    limit: int | None,
) -> tuple[BenchPlayer, ...]:
    failure_by_slot: dict[str, float] = defaultdict(float)
    for starter in starters:
        failure_by_slot[starter.slot] += 1 - starter.appearance_probability
    ordered: list[BenchPlayer] = []
    for index, player in enumerate(players):
        if index in starter_indices or not player.available:
            continue
        coverage = max((failure_by_slot.get(role, 0.0) for role in player.roles), default=0.0)

        utility = player.expected_points * (1 + coverage)
        ordered.append(
            BenchPlayer(
                player_id=player.player_id,
                display_name=player.display_name,
                roles=player.roles,
                utility=utility,
            )
        )
    ordered.sort(key=lambda player: (-player.utility, player.player_id))
    if limit is not None:
        ordered = ordered[:limit]
    return tuple(ordered)
