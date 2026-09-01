from __future__ import annotations

from collections import defaultdict

import numpy as np
from numpy.typing import NDArray
from ortools.sat.python import cp_model

from markguardiola.decision.lineup import NoLegalLineupError, order_bench
from markguardiola.decision.models import (
    LineupDecision,
    MatchupDecision,
    PlayerDecisionInput,
    SelectedPlayer,
)
from markguardiola.domain.enums import RiskMode
from markguardiola.fantasy.rules import Formation


class MatchupOptimizer:
    def __init__(self, *, maximum_scenarios: int = 500, time_limit_seconds: float = 20.0) -> None:
        self._maximum_scenarios = maximum_scenarios
        self._time_limit_seconds = time_limit_seconds

    def optimize(
        self,
        players: list[PlayerDecisionInput],
        opponent_score_samples: NDArray[np.float64],
        formations: tuple[Formation, ...],
    ) -> MatchupDecision:
        sample_count = opponent_score_samples.size
        if sample_count < 1:
            raise ValueError()
        if any(player.samples is None or player.samples.size != sample_count for player in players):
            raise ValueError()
        player_samples: list[NDArray[np.float64]] = []
        for player in players:
            assert player.samples is not None
            player_samples.append(player.samples)
        scenario_indices = np.linspace(
            0,
            sample_count - 1,
            min(sample_count, self._maximum_scenarios),
            dtype=int,
        )
        model = cp_model.CpModel()
        formation_selected = [
            model.new_bool_var(f"formation_{index}") for index in range(len(formations))
        ]
        model.add_exactly_one(formation_selected)
        assignments: dict[tuple[int, int, int], cp_model.IntVar] = {}
        by_player: dict[int, list[cp_model.IntVar]] = defaultdict(list)
        for formation_index, formation in enumerate(formations):
            for slot_index, slot in enumerate(formation.slots):
                slot_vars: list[cp_model.IntVar] = []
                for player_index, player in enumerate(players):
                    if not player.available or slot not in player.roles:
                        continue
                    variable = model.new_bool_var(
                        f"assign_{formation_index}_{slot_index}_{player_index}"
                    )
                    assignments[(formation_index, slot_index, player_index)] = variable
                    by_player[player_index].append(variable)
                    slot_vars.append(variable)
                if slot_vars:
                    model.add(sum(slot_vars) == formation_selected[formation_index])
                else:
                    model.add(formation_selected[formation_index] == 0)
        selected: dict[int, cp_model.IntVar] = {}
        for player_index, variables in by_player.items():
            model.add(sum(variables) <= 1)
            chosen = model.new_bool_var(f"selected_{player_index}")
            model.add(chosen == sum(variables))
            selected[player_index] = chosen

        point_scale = 100
        scenario_outcomes: list[tuple[cp_model.IntVar, cp_model.IntVar, cp_model.IntVar]] = []
        for scenario_number, sample_index in enumerate(scenario_indices):
            user_score = cp_model.LinearExpr.sum(
                [
                    round(float(player_samples[player_index][sample_index]) * point_scale)
                    * variable
                    for player_index, variable in selected.items()
                ]
            )
            opponent_score = round(float(opponent_score_samples[sample_index]) * point_scale)
            difference = user_score - opponent_score
            win = model.new_bool_var(f"win_{scenario_number}")
            draw = model.new_bool_var(f"draw_{scenario_number}")
            loss = model.new_bool_var(f"loss_{scenario_number}")
            model.add_exactly_one(win, draw, loss)
            model.add(difference >= 1).only_enforce_if(win)
            model.add(difference == 0).only_enforce_if(draw)
            model.add(difference <= -1).only_enforce_if(loss)
            scenario_outcomes.append((win, draw, loss))

        expected_tiebreak = sum(
            round(players[index].expected_points * point_scale) * variable
            for index, variable in selected.items()
        )
        maximum_tiebreak = max(
            1,
            round(
                sum(sorted((p.expected_points for p in players), reverse=True)[:11]) * point_scale
            )
            + 1,
        )
        model.maximize(
            sum(2 * win + draw for win, draw, _loss in scenario_outcomes) * maximum_tiebreak
            + expected_tiebreak
        )
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = self._time_limit_seconds
        solver.parameters.num_search_workers = 1
        solver.parameters.random_seed = 2026
        status = solver.solve(model)
        if status not in {cp_model.OPTIMAL, cp_model.FEASIBLE}:
            raise NoLegalLineupError()

        formation_index = next(
            index
            for index, variable in enumerate(formation_selected)
            if solver.boolean_value(variable)
        )
        formation = formations[formation_index]
        starter_indices: set[int] = set()
        starters: list[SelectedPlayer] = []
        for (candidate_formation, slot_index, player_index), variable in assignments.items():
            if candidate_formation != formation_index or not solver.boolean_value(variable):
                continue
            player = players[player_index]
            starter_indices.add(player_index)
            starters.append(
                SelectedPlayer(
                    player_id=player.player_id,
                    display_name=player.display_name,
                    slot=formation.slots[slot_index],
                    expected_points=player.expected_points,
                    appearance_probability=player.appearance_probability,
                )
            )
        starters.sort(key=lambda item: (formation.slots.index(item.slot), item.player_id))
        user_scores = np.sum(
            np.stack([player_samples[index] for index in starter_indices]),
            axis=0,
        )
        wins = float(np.mean(user_scores > opponent_score_samples))
        draws = float(np.mean(np.isclose(user_scores, opponent_score_samples)))
        losses = max(0.0, 1.0 - wins - draws)
        lineup = LineupDecision(
            formation=formation.name,
            risk_mode=RiskMode.MATCHUP,
            starters=tuple(starters),
            bench=order_bench(players, starter_indices, starters, limit=None),
            objective_value=wins + 0.5 * draws,
            expected_points=sum(players[index].expected_points for index in starter_indices),
            p10_points=float(np.quantile(user_scores, 0.1)),
            p90_points=float(np.quantile(user_scores, 0.9)),
        )
        return MatchupDecision(
            lineup=lineup,
            win_probability=wins,
            draw_probability=draws,
            loss_probability=losses,
            scenario_count=len(scenario_indices),
        )
