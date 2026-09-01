from __future__ import annotations

from collections import defaultdict
from math import isfinite

import numpy as np
from numpy.random import Generator

from markguardiola.simulation.models import (
    FixtureForecast,
    FixtureSimulationResult,
    PlayerForecast,
    PlayerSamples,
    PlayerSimulationSummary,
)


class SimulationInputError(ValueError):
    pass


class FixtureSimulator:
    def simulate(
        self,
        forecast: FixtureForecast,
        *,
        simulation_count: int = 10_000,
        seed: int | None = None,
    ) -> FixtureSimulationResult:
        if simulation_count < 1:
            raise SimulationInputError()
        _validate_fixture(forecast)
        random = np.random.default_rng(seed)
        home_goals, away_goals = _sample_correlated_goals(
            random,
            forecast.home_goals_mean,
            forecast.away_goals_mean,
            forecast.shared_goal_correlation,
            simulation_count,
        )
        samples = {
            player.player_id: _empty_player_samples(player, simulation_count)
            for player in forecast.players
        }
        by_team: dict[str, list[PlayerForecast]] = defaultdict(list)
        for player in forecast.players:
            by_team[player.team_id].append(player)

        for index in range(simulation_count):
            lineups = {
                team_id: _sample_team_lineup(random, players, forecast.maximum_substitutions)
                for team_id, players in by_team.items()
            }
            for team_id, outcome in lineups.items():
                for player, started, minutes in outcome:
                    player_sample = samples[player.player_id]
                    player_sample.started[index] = started
                    player_sample.minutes[index] = minutes

                scored = int(
                    home_goals[index] if team_id == forecast.home_team_id else away_goals[index]
                )
                conceded = int(
                    away_goals[index] if team_id == forecast.home_team_id else home_goals[index]
                )
                _allocate_team_events(
                    random,
                    outcome,
                    lineups[
                        forecast.away_team_id
                        if team_id == forecast.home_team_id
                        else forecast.home_team_id
                    ],
                    samples,
                    index,
                    scored,
                    conceded,
                    forecast,
                    forecast.home_goals_mean
                    if team_id == forecast.home_team_id
                    else forecast.away_goals_mean,
                    forecast.away_goals_mean
                    if team_id == forecast.home_team_id
                    else forecast.home_goals_mean,
                )

        summaries = {
            player_id: _summarize_player(player_samples)
            for player_id, player_samples in samples.items()
        }
        return FixtureSimulationResult(
            match_id=forecast.match_id,
            simulation_count=simulation_count,
            seed=seed,
            home_goals=home_goals,
            away_goals=away_goals,
            player_samples=samples,
            summaries=summaries,
        )


def _validate_fixture(forecast: FixtureForecast) -> None:
    if forecast.home_team_id == forecast.away_team_id:
        raise SimulationInputError()
    if any(
        not isfinite(value) or value < 0
        for value in (forecast.home_goals_mean, forecast.away_goals_mean)
    ):
        raise SimulationInputError()
    if not 0 <= forecast.shared_goal_correlation <= 1:
        raise SimulationInputError()
    if not 0 <= forecast.assisted_goal_probability <= 1:
        raise SimulationInputError()
    if not 0 <= forecast.maximum_substitutions <= 10:
        raise SimulationInputError()
    if (rates := forecast.rare_event_rates) and (
        not 0 <= rates.penalty_goal_share <= 1
        or not 0 <= rates.own_goal_share <= 1
        or rates.penalty_goal_share + rates.own_goal_share > 1 + 1e-12
        or not 0 <= rates.penalty_save_probability <= 1
        or not isfinite(rates.missed_penalties_per_goal)
        or rates.missed_penalties_per_goal < 0
    ):
        raise SimulationInputError()
    ids = [player.player_id for player in forecast.players]
    if len(ids) != len(set(ids)):
        raise SimulationInputError()
    expected_teams = {forecast.home_team_id, forecast.away_team_id}
    if {player.team_id for player in forecast.players} != expected_teams:
        raise SimulationInputError()
    for team_id in expected_teams:
        team_players = [player for player in forecast.players if player.team_id == team_id]
        goalkeepers = [player for player in team_players if player.position == "GK"]
        outfield = [player for player in team_players if player.position != "GK"]
        if not goalkeepers or len(outfield) < 10:
            raise SimulationInputError()
    for player in forecast.players:
        probabilities = (
            player.availability_probability,
            player.start_probability,
            player.appearance_probability,
            player.yellow_card_probability,
            player.red_card_probability,
            player.reliability,
        )
        if any(not 0 <= value <= 1 for value in probabilities):
            raise SimulationInputError()
        if player.start_probability > player.appearance_probability:
            raise SimulationInputError()
        if any(
            not isfinite(value) or value < 0
            for value in (player.expected_minutes, player.minutes_stddev)
        ):
            raise SimulationInputError()
        if any(
            not isfinite(value) or value < 0
            for value in (
                player.goal_weight,
                player.assist_weight,
                player.saves_per90,
                player.penalty_weight,
                player.own_goal_weight,
            )
        ):
            raise SimulationInputError()
    for team_id in expected_teams:
        team_players = [player for player in forecast.players if player.team_id == team_id]
        confirmed = [player for player in team_players if player.confirmed_start is True]
        if any(player.confirmed_start is not None for player in team_players) and (
            len(confirmed) != 11
            or sum(player.position == "GK" for player in confirmed) != 1
            or any(player.availability_probability != 1 for player in confirmed)
        ):
            raise SimulationInputError()


def _sample_correlated_goals(
    random: Generator,
    home_mean: float,
    away_mean: float,
    correlation: float,
    count: int,
) -> tuple[np.ndarray, np.ndarray]:
    shared_mean = correlation * min(home_mean, away_mean)
    shared = random.poisson(shared_mean, size=count)
    home = shared + random.poisson(max(home_mean - shared_mean, 0), size=count)
    away = shared + random.poisson(max(away_mean - shared_mean, 0), size=count)
    return home.astype(np.int16), away.astype(np.int16)


def _sample_team_lineup(
    random: Generator, players: list[PlayerForecast], maximum_substitutions: int
) -> list[tuple[PlayerForecast, bool, int]]:
    goalkeepers = [player for player in players if player.position == "GK"]
    outfield = [player for player in players if player.position != "GK"]
    available_goalkeepers, available_outfield = _conditional_availability(
        random, goalkeepers, outfield
    )
    confirmed = [player for player in players if player.confirmed_start is True]
    if confirmed:
        goalkeeper = next(player for player in confirmed if player.position == "GK")
        starters = [player for player in confirmed if player.position != "GK"]
    else:
        goalkeeper = _weighted_choice(random, available_goalkeepers, "start_probability")
        starters = _weighted_without_replacement(
            random, available_outfield, 10, "start_probability"
        )
    starter_ids = {player.player_id for player in starters}
    substitutes: list[PlayerForecast] = []
    for player in available_outfield:
        if player.player_id in starter_ids:
            continue
        denominator = max(1 - player.start_probability, 1e-9)
        conditional_sub_probability = np.clip(
            (player.appearance_probability - player.start_probability) / denominator,
            0,
            1,
        )
        if random.random() < conditional_sub_probability:
            substitutes.append(player)
    if len(substitutes) > maximum_substitutions:
        substitutes = (
            _weighted_without_replacement(
                random, substitutes, maximum_substitutions, "appearance_probability"
            )
            if maximum_substitutions
            else []
        )
    appearing_outfield = starters + substitutes
    raw_minutes = np.clip(
        random.normal(
            [player.expected_minutes for player in appearing_outfield],
            [max(player.minutes_stddev, 1.0) for player in appearing_outfield],
        ),
        1,
        90,
    )

    allocated = 1 + _project_capped_minutes(
        raw_minutes - 1, total=900 - len(appearing_outfield), cap=89
    )
    output = [(goalkeeper, True, 90)]
    output.extend(
        (player, player.player_id in starter_ids, int(minutes))
        for player, minutes in zip(appearing_outfield, allocated, strict=True)
    )
    return output


def _conditional_availability(
    random: Generator,
    goalkeepers: list[PlayerForecast],
    outfield: list[PlayerForecast],
) -> tuple[list[PlayerForecast], list[PlayerForecast]]:
    for _ in range(50):
        available_goalkeepers = [
            player for player in goalkeepers if random.random() < player.availability_probability
        ]
        available_outfield = [
            player for player in outfield if random.random() < player.availability_probability
        ]
        if available_goalkeepers and len(available_outfield) >= 10:
            return available_goalkeepers, available_outfield
    raise SimulationInputError()


def _weighted_choice(
    random: Generator, players: list[PlayerForecast], attribute: str
) -> PlayerForecast:
    weights = np.array([max(float(getattr(player, attribute)), 1e-9) for player in players])
    probabilities = weights / weights.sum()
    return players[int(random.choice(len(players), p=probabilities))]


def _weighted_without_replacement(
    random: Generator,
    players: list[PlayerForecast],
    count: int,
    attribute: str,
) -> list[PlayerForecast]:
    weights = np.array([max(float(getattr(player, attribute)), 1e-9) for player in players])
    gumbels = random.gumbel(size=len(players))
    keys = np.log(weights) + gumbels
    indices = np.argpartition(keys, -count)[-count:]
    return [players[int(index)] for index in indices]


def _project_capped_minutes(raw: np.ndarray, *, total: int, cap: int) -> np.ndarray:
    if total < 0 or cap < 0 or raw.size * cap < total or not np.all(np.isfinite(raw)):
        raise SimulationInputError()
    if total == 0:
        return np.zeros(raw.size, dtype=np.int16)
    if total == raw.size * cap:
        return np.full(raw.size, cap, dtype=np.int16)

    breakpoints = np.concatenate((-raw, cap - raw))
    order = np.argsort(breakpoints)
    points = breakpoints[order]
    slope = np.cumsum(np.concatenate((np.ones(raw.size), -np.ones(raw.size)))[order])
    cumulative = np.concatenate(([0.0], np.cumsum(np.diff(points) * slope[:-1])))
    segment = max(0, int(np.searchsorted(cumulative, total, side="left")) - 1)
    shift = points[segment] + (total - cumulative[segment]) / slope[segment]
    values = np.clip(raw + shift, 0, cap)
    floored = np.floor(values).astype(np.int16)
    remainder = total - int(floored.sum())
    if remainder:
        fractions = values - floored
        eligible = np.flatnonzero(floored < cap)
        ranked = eligible[np.argsort(fractions[eligible])[::-1]]
        floored[ranked[:remainder]] += 1
    if int(floored.sum()) != total or np.any(floored > cap):
        raise RuntimeError()
    return np.asarray(floored, dtype=np.int16)


def _allocate_team_events(
    random: Generator,
    lineup: list[tuple[PlayerForecast, bool, int]],
    opponents: list[tuple[PlayerForecast, bool, int]],
    samples: dict[str, PlayerSamples],
    index: int,
    team_goals: int,
    conceded: int,
    forecast: FixtureForecast,
    goals_mean: float,
    conceded_mean: float,
) -> None:
    players = [item[0] for item in lineup]
    minutes = np.array([item[2] for item in lineup], dtype=float)
    penalty_goals = own_goals = missed_penalties = 0
    expected_penalty_saves = 0.0
    if rates := forecast.rare_event_rates:
        penalty_goals, own_goals, team_goals = random.multinomial(
            team_goals,
            [
                rates.penalty_goal_share,
                rates.own_goal_share,
                max(0.0, 1 - rates.penalty_goal_share - rates.own_goal_share),
            ],
        )
        missed_penalties = int(random.poisson(goals_mean * rates.missed_penalties_per_goal))
        saved_penalties = random.binomial(missed_penalties, rates.penalty_save_probability)
        opposing_keeper = next(player for player, _, _ in opponents if player.position == "GK")
        samples[opposing_keeper.player_id].penalties_saved[index] = saved_penalties
        samples[opposing_keeper.player_id].saves[index] += saved_penalties
        expected_penalty_saves = (
            conceded_mean * rates.missed_penalties_per_goal * rates.penalty_save_probability
        )
        _allocate_rare_counts(
            random, opponents, samples, index, int(own_goals), "own_goal_weight", "own_goals"
        )
        _allocate_rare_counts(
            random, lineup, samples, index, int(penalty_goals), "penalty_weight", "penalties_scored"
        )
        _allocate_rare_counts(
            random, lineup, samples, index, missed_penalties, "penalty_weight", "penalties_missed"
        )
    goal_weights = np.array([player.goal_weight for player in players]) * minutes
    if goal_weights.sum() <= 0:
        goal_weights = (
            np.array([0 if player.position == "GK" else 1 for player in players]) * minutes
        )
    scorer_counts = random.multinomial(team_goals, goal_weights / goal_weights.sum())
    for player, goals in zip(players, scorer_counts, strict=True):
        sample = samples[player.player_id]
        sample.goals[index] = goals + sample.penalties_scored[index]

    for scorer_index, goals in enumerate(scorer_counts):
        for _ in range(int(goals)):
            if random.random() >= forecast.assisted_goal_probability:
                continue
            assist_weights = np.array([player.assist_weight for player in players]) * minutes
            assist_weights[scorer_index] = 0
            if assist_weights.sum() <= 0:
                continue
            assister = int(random.choice(len(players), p=assist_weights / assist_weights.sum()))
            samples[players[assister].player_id].assists[index] += 1

    for player, _, played_minutes in lineup:
        player_samples = samples[player.player_id]
        fraction = played_minutes / 90
        player_samples.clean_sheet[index] = conceded == 0 and played_minutes >= 60
        yellow_probability = 1 - (1 - player.yellow_card_probability) ** fraction
        red_probability = 1 - (1 - player.red_card_probability) ** fraction
        player_samples.yellow_cards[index] = int(random.random() < yellow_probability)
        player_samples.red_cards[index] = int(random.random() < red_probability)
        if player.position == "GK":
            player_samples.goals_conceded[index] = conceded

            player_samples.saves[index] += random.poisson(
                max(0.0, player.saves_per90 * fraction - expected_penalty_saves)
            )


def _allocate_rare_counts(
    random: Generator,
    lineup: list[tuple[PlayerForecast, bool, int]],
    samples: dict[str, PlayerSamples],
    index: int,
    count: int,
    weight: str,
    event: str,
) -> None:
    if count == 0:
        return
    weights = np.array([getattr(player, weight) * minutes for player, _, minutes in lineup])
    if weights.sum() <= 0:
        weights = np.array(
            [
                minutes if weight == "own_goal_weight" or player.position != "GK" else 0
                for player, _, minutes in lineup
            ],
            dtype=float,
        )
    allocated = random.multinomial(count, weights / weights.sum())
    for (player, _, _), value in zip(lineup, allocated, strict=True):
        getattr(samples[player.player_id], event)[index] = value


def _empty_player_samples(player: PlayerForecast, count: int) -> PlayerSamples:
    return PlayerSamples(
        player_id=player.player_id,
        team_id=player.team_id,
        started=np.zeros(count, dtype=bool),
        minutes=np.zeros(count, dtype=np.int16),
        goals=np.zeros(count, dtype=np.int16),
        assists=np.zeros(count, dtype=np.int16),
        clean_sheet=np.zeros(count, dtype=bool),
        yellow_cards=np.zeros(count, dtype=np.int16),
        red_cards=np.zeros(count, dtype=np.int16),
        saves=np.zeros(count, dtype=np.int16),
        goals_conceded=np.zeros(count, dtype=np.int16),
        penalties_scored=np.zeros(count, dtype=np.int16),
        penalties_missed=np.zeros(count, dtype=np.int16),
        penalties_saved=np.zeros(count, dtype=np.int16),
        own_goals=np.zeros(count, dtype=np.int16),
    )


def _summarize_player(samples: PlayerSamples) -> PlayerSimulationSummary:
    return PlayerSimulationSummary(
        player_id=samples.player_id,
        mean_minutes=float(np.mean(samples.minutes)),
        median_minutes=float(np.median(samples.minutes)),
        p10_minutes=float(np.quantile(samples.minutes, 0.1)),
        p90_minutes=float(np.quantile(samples.minutes, 0.9)),
        start_probability=float(np.mean(samples.started)),
        appearance_probability=float(np.mean(samples.minutes > 0)),
        goal_probability=float(np.mean(samples.goals > 0)),
        assist_probability=float(np.mean(samples.assists > 0)),
        clean_sheet_probability=float(np.mean(samples.clean_sheet)),
        yellow_card_probability=float(np.mean(samples.yellow_cards > 0)),
        red_card_probability=float(np.mean(samples.red_cards > 0)),
        mean_saves=float(np.mean(samples.saves)),
        mean_goals_conceded=float(np.mean(samples.goals_conceded)),
        mean_penalties_scored=float(np.mean(samples.penalties_scored)),
        mean_penalties_missed=float(np.mean(samples.penalties_missed)),
        mean_penalties_saved=float(np.mean(samples.penalties_saved)),
        mean_own_goals=float(np.mean(samples.own_goals)),
    )
