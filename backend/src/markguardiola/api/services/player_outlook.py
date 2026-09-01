from __future__ import annotations

import uuid

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from markguardiola.api.contracts import (
    ExplanationView,
    PlayerFixtureOutlook,
    PlayerFootballOutlook,
    PlayerOutlookView,
    PlayerRecommendationScore,
)
from markguardiola.api.services.context import parse_scoring_rules
from markguardiola.api.services.fixture_simulations import ScoredFixturePlayer
from markguardiola.api.services.projections import load_player_projection_bundle
from markguardiola.api.services.views import match_summary
from markguardiola.db.models import LeagueRule, Match, PredictionRun, Team
from markguardiola.insights import ExplanationEngine, InsightEvidence


async def load_player_outlook(
    session: AsyncSession,
    *,
    league_id: uuid.UUID,
    player_id: uuid.UUID,
    rule: LeagueRule,
    horizon: int,
) -> PlayerOutlookView:
    scoring = parse_scoring_rules(rule)
    bundle = await load_player_projection_bundle(
        session, league_id=league_id, player_ids=[player_id], rules=scoring, horizon=horizon
    )
    player = bundle.inputs[0]
    match_ids = [uuid.UUID(projection.fixture_id) for projection in player.fixture_projections]
    matches = {
        match.id: match
        for match in (await session.scalars(select(Match).where(Match.id.in_(match_ids)))).all()
    }
    team_ids = {
        team for match in matches.values() for team in (match.home_team_id, match.away_team_id)
    }
    teams = {
        team.id: team
        for team in (await session.scalars(select(Team).where(Team.id.in_(team_ids)))).all()
    }
    fixtures = []
    for match_id in match_ids:
        scenario = bundle.fixture_scenarios[(match_id, player_id)]
        expected = float(np.mean(scenario.samples))
        fixtures.append(
            PlayerFixtureOutlook(
                match=match_summary(matches[match_id], teams),
                expected_points=expected,
                median_points=float(np.median(scenario.samples)),
                p10_points=float(np.quantile(scenario.samples, 0.1)),
                p90_points=float(np.quantile(scenario.samples, 0.9)),
                available=scenario.available,
                scoring_appearance_probability=float(np.mean(scenario.appearance_samples)),
                confidence=scenario.confidence,
                football=PlayerFootballOutlook.model_validate(scenario.football),
                explanations=_explanations(scenario, expected),
            )
        )
    warnings = list(bundle.warnings)
    if len(fixtures) < horizon:
        warnings.append(
            f"Disponibili {len(fixtures)} delle {horizon} partite richieste: "
            "le previsioni mancanti non vengono estrapolate."
        )
    if scoring.defensive_modifier_enabled:
        warnings.append(
            "Il modificatore difensivo dipende dalla formazione: "
            "non è incluso nei fantapunti individuali."
        )
    run = await session.get_one(PredictionRun, bundle.prediction_run_id)
    return PlayerOutlookView(
        player_id=player_id,
        league_id=league_id,
        rules_version=rule.version,
        roles=player.roles,
        scoring_role=player.scoring_role,
        recommendation_score=PlayerRecommendationScore(value=player.expected_points),
        requested_horizon=horizon,
        fixtures=fixtures,
        prediction_run_id=bundle.prediction_run_id,
        model_versions=run.model_versions,
        prediction_cutoff=bundle.prediction_cutoff,
        data_cutoff=bundle.data_cutoff,
        decision_cutoff=bundle.decision_cutoff,
        simulation_count=bundle.simulation_count,
        seed=bundle.seed,
        warnings=tuple(warnings),
    )


def _explanations(scenario: ScoredFixturePlayer, expected: float) -> tuple[ExplanationView, ...]:
    evidence = [
        InsightEvidence(
            "player_expected_points",
            expected,
            1.0,
            scenario.confidence,
            "league_scored_fixture_scenarios.mean",
        ),
        InsightEvidence(
            "scoring_appearance_probability",
            float(np.mean(scenario.appearance_samples)),
            2.0,
            scenario.confidence,
            "league_scored_fixture_scenarios.appearance",
        ),
        InsightEvidence(
            "expected_minutes",
            scenario.football.mean_minutes,
            0.9,
            scenario.confidence,
            "fixture_scenarios.mean_minutes",
        ),
        InsightEvidence(
            "goal_probability",
            scenario.football.goal_probability,
            1.2,
            scenario.confidence,
            "fixture_scenarios.goal_probability",
        ),
    ]
    if not scenario.available:
        evidence.append(
            InsightEvidence(
                "player_unavailable", 1.0, 5.0, 1.0, "operational_availability_at_decision_cutoff"
            )
        )
    reasons = ExplanationEngine().explain(evidence, overall_confidence=scenario.confidence)
    return tuple(ExplanationView.model_validate(reason) for reason in reasons)
