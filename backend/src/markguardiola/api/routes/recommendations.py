from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Annotated

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from markguardiola.api.contracts import (
    BenchPlayerView,
    ExplanationView,
    LineupRecommendationRequest,
    LineupRecommendationView,
    MarketRecommendationItem,
    MarketRecommendationRequest,
    MarketRecommendationView,
    MatchupRecommendationRequest,
    MatchupRecommendationView,
    SelectedPlayerView,
)
from markguardiola.api.services.context import (
    get_active_rules,
    get_fantasy_team,
    get_league,
    parse_formations,
    parse_scoring_rules,
)
from markguardiola.api.services.projections import (
    PredictionDataUnavailableError,
    ProjectionBundle,
    load_player_projection_bundle,
    load_roster_projection_bundle,
)
from markguardiola.api.services.roster_rules import enforce_roster, load_roster_roles
from markguardiola.db.models import (
    Budget,
    LineupRecommendation,
    MarketEntry,
    MarketRecommendation,
    RecommendationExplanation,
    SimulationRun,
)
from markguardiola.db.session import get_db_session
from markguardiola.decision import (
    MarketCandidate,
    MarketOptimizer,
    MatchupOptimizer,
    NoLegalLineupError,
)
from markguardiola.decision.models import LineupDecision
from markguardiola.decision.scenario_search import ScenarioLineupOptimizer
from markguardiola.domain.enums import RiskMode
from markguardiola.fantasy.roster import RosterConstraints, validate_roster
from markguardiola.fantasy.rules.models import SubstitutionRules
from markguardiola.insights import Explanation, ExplanationEngine, InsightEvidence

router = APIRouter(prefix="/api/v1/leagues/{league_id}/recommendations", tags=["decisions"])
Session = Annotated[AsyncSession, Depends(get_db_session)]


@router.post(
    "/lineup",
    response_model=LineupRecommendationView,
    operation_id="recommendLineup",
)
async def recommend_lineup(
    league_id: uuid.UUID,
    payload: LineupRecommendationRequest,
    session: Session,
) -> LineupRecommendationView:
    league = await get_league(session, league_id)
    team = await get_fantasy_team(session, league_id, payload.fantasy_team_id)
    rule = await get_active_rules(session, league_id)
    enforce_roster(
        validate_roster(
            await load_roster_roles(session, league_id, team.id, league.mode),
            RosterConstraints.model_validate(rule.roster_constraints),
        )
    )
    bundle = await _roster_bundle_or_409(
        session,
        league_id,
        team.id,
        parse_scoring_rules(rule),
    )
    try:
        decision = await asyncio.to_thread(
            ScenarioLineupOptimizer(
                parse_scoring_rules(rule),
                SubstitutionRules.model_validate(rule.substitution_rules),
            ).optimize,
            bundle.inputs,
            parse_formations(rule),
            risk_mode=payload.risk_mode,
            bench_size=payload.bench_size,
        )
    except NoLegalLineupError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT) from None
    simulation = await _create_simulation_run(
        session,
        bundle,
        league_id,
        rule.version,
        simulation_count=bundle.simulation_count,
        seed=bundle.seed,
        method="coherent_fixture_monte_carlo",
        decision=decision,
    )
    explanations = _lineup_explanations(decision, bundle)
    persisted = await _persist_lineup(
        session,
        simulation.id,
        league_id,
        team.id,
        decision,
        bundle,
        explanations,
    )
    await session.commit()
    return _lineup_view(persisted.id, team.id, decision, bundle, explanations)


@router.post(
    "/market",
    response_model=MarketRecommendationView,
    operation_id="recommendMarket",
)
async def recommend_market(
    league_id: uuid.UUID,
    payload: MarketRecommendationRequest,
    session: Session,
) -> MarketRecommendationView:
    league = await get_league(session, league_id)
    team = await get_fantasy_team(session, league_id, payload.fantasy_team_id)
    rule = await get_active_rules(session, league_id)
    roster_constraints = RosterConstraints.model_validate(rule.roster_constraints)
    owned_roles = await load_roster_roles(session, league_id, team.id, league.mode)
    enforce_roster(validate_roster(owned_roles, roster_constraints))
    scoring = parse_scoring_rules(rule)
    roster_bundle = await _roster_bundle_or_409(
        session,
        league_id,
        team.id,
        scoring,
        horizon=payload.horizon,
    )
    market_rows = list(
        (
            await session.scalars(
                select(MarketEntry).where(
                    MarketEntry.league_id == league_id,
                    MarketEntry.available.is_(True),
                )
            )
        ).all()
    )
    if not market_rows:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT)
    try:
        market_bundle = await load_player_projection_bundle(
            session,
            league_id=league_id,
            player_ids=[entry.player_id for entry in market_rows],
            rules=scoring,
            decision_cutoff=roster_bundle.decision_cutoff,
            prediction_run_id=roster_bundle.prediction_run_id,
            horizon=payload.horizon,
        )
    except PredictionDataUnavailableError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT) from None
    projected_by_id = {uuid.UUID(item.player_id): item for item in market_bundle.inputs}
    photo_by_id = {
        item.player_id: item.photo_url for item in (*roster_bundle.inputs, *market_bundle.inputs)
    }
    candidates = [
        MarketCandidate(
            player=projected_by_id[entry.player_id],
            asking_price=float(entry.asking_price) if entry.asking_price is not None else None,
            available=entry.available,
        )
        for entry in market_rows
        if entry.player_id in projected_by_id
    ]
    budget = await _latest_budget(session, team.id)
    remaining_budget = float(budget.remaining_credits) if budget is not None else None
    try:
        ranked = await asyncio.to_thread(
            MarketOptimizer(
                scoring_rules=scoring,
                substitution_rules=SubstitutionRules.model_validate(rule.substitution_rules),
            ).rank_acquisitions,
            roster=roster_bundle.inputs,
            candidates=candidates,
            formations=parse_formations(rule),
            remaining_budget=remaining_budget,
            recover_purchase_price=payload.recover_purchase_price,
            limit=payload.limit,
            optimization_horizon=payload.horizon,
            roster_constraints=roster_constraints,
            owned_roles=owned_roles,
        )
    except NoLegalLineupError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT) from None
    simulation = await _create_simulation_run(
        session,
        roster_bundle,
        league_id,
        rule.version,
        simulation_count=roster_bundle.simulation_count,
        seed=roster_bundle.seed,
        method="coherent_fixture_value_over_replacement",
    )
    items: list[MarketRecommendationItem] = []
    for rank, result in enumerate(ranked, start=1):
        confidence = min(roster_bundle.confidence, market_bundle.confidence)
        explanations = ExplanationEngine().explain(
            [
                InsightEvidence(
                    key="lineup_expected_delta",
                    value=result.expected_improvement,
                    impact=result.expected_improvement,
                    reliability=confidence,
                    source_feature="optimized_roster_expected_points",
                ),
                InsightEvidence(
                    key="role_flexibility_delta",
                    value=float(result.role_flexibility_delta),
                    impact=float(result.role_flexibility_delta),
                    reliability=confidence,
                    source_feature="legal_formation_count",
                ),
            ],
            overall_confidence=confidence,
        )
        recommendation = MarketRecommendation(
            simulation_run_id=simulation.id,
            league_id=league_id,
            fantasy_team_id=team.id,
            target_player_id=uuid.UUID(result.target_player_id),
            replace_player_id=uuid.UUID(result.replace_player_id),
            rank=rank,
            horizon=result.optimization_horizon,
            expected_improvement=result.expected_improvement,
            value_over_replacement=result.value_over_replacement,
            budget_efficiency=result.budget_efficiency,
            confidence=confidence,
            detail={
                "asking_price": result.price,
                "affordability": result.affordability,
                "formation_before": result.formation_before,
                "formation_after": result.formation_after,
                "horizon_improvements": result.horizon_improvements,
                "role_flexibility_delta": result.role_flexibility_delta,
                "evaluation_method": result.evaluation_method,
                "formation_schedule_before": result.formation_schedule_before,
                "formation_schedule_after": result.formation_schedule_after,
            },
        )
        session.add(recommendation)
        await session.flush()
        await _persist_explanations(session, "market", recommendation.id, explanations)
        items.append(
            MarketRecommendationItem(
                recommendation_id=recommendation.id,
                target_player_id=uuid.UUID(result.target_player_id),
                target_name=result.target_name,
                target_photo_url=photo_by_id.get(result.target_player_id),
                replace_player_id=uuid.UUID(result.replace_player_id),
                replace_name=result.replace_name,
                replace_photo_url=photo_by_id.get(result.replace_player_id),
                asking_price=result.price,
                affordability=result.affordability,
                optimization_horizon=result.optimization_horizon,
                evaluation_method=result.evaluation_method,
                formation_schedule_before=result.formation_schedule_before,
                formation_schedule_after=result.formation_schedule_after,
                expected_improvement=result.expected_improvement,
                value_over_replacement=result.value_over_replacement,
                budget_efficiency=result.budget_efficiency,
                formation_before=result.formation_before,
                formation_after=result.formation_after,
                horizon_improvements=result.horizon_improvements,
                role_flexibility_delta=result.role_flexibility_delta,
                confidence=confidence,
                explanations=_explanation_views(explanations),
            )
        )
    await session.commit()
    return MarketRecommendationView(
        fantasy_team_id=team.id,
        remaining_budget=remaining_budget,
        data_cutoff=roster_bundle.data_cutoff,
        decision_cutoff=roster_bundle.decision_cutoff,
        items=items,
        warnings=tuple(dict.fromkeys((*roster_bundle.warnings, *market_bundle.warnings))),
    )


@router.post(
    "/matchup",
    response_model=MatchupRecommendationView,
    operation_id="recommendMatchup",
)
async def recommend_matchup(
    league_id: uuid.UUID,
    payload: MatchupRecommendationRequest,
    session: Session,
) -> MatchupRecommendationView:
    league = await get_league(session, league_id)
    if not league.head_to_head_enabled:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT)
    team = await get_fantasy_team(session, league_id, payload.fantasy_team_id)
    opponent = await get_fantasy_team(
        session,
        league_id,
        payload.opponent_fantasy_team_id,
        user_team_default=False,
    )
    if opponent.id == team.id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)
    rule = await get_active_rules(session, league_id)
    scoring = parse_scoring_rules(rule)
    for fantasy_team in (team, opponent):
        enforce_roster(
            validate_roster(
                await load_roster_roles(session, league_id, fantasy_team.id, league.mode),
                RosterConstraints.model_validate(rule.roster_constraints),
            )
        )
    user_bundle = await _roster_bundle_or_409(
        session,
        league_id,
        team.id,
        scoring,
        simulation_count=payload.simulation_count,
        seed=payload.seed,
    )
    opponent_bundle = await _roster_bundle_or_409(
        session,
        league_id,
        opponent.id,
        scoring,
        simulation_count=payload.simulation_count,
        seed=payload.seed,
        decision_cutoff=user_bundle.decision_cutoff,
        prediction_run_id=user_bundle.prediction_run_id,
    )
    formations = parse_formations(rule)
    try:
        substitution_rules = SubstitutionRules.model_validate(rule.substitution_rules)
        opponent_lineup = await asyncio.to_thread(
            ScenarioLineupOptimizer(scoring, substitution_rules).optimize,
            opponent_bundle.inputs,
            formations,
        )
        assert opponent_lineup.score_samples is not None
        opponent_samples = opponent_lineup.score_samples
        decision = await asyncio.to_thread(
            MatchupOptimizer().optimize,
            user_bundle.inputs,
            opponent_samples,
            formations,
        )

        from dataclasses import replace

        scored_lineup = await asyncio.to_thread(
            ScenarioLineupOptimizer(scoring, substitution_rules).optimize,
            user_bundle.inputs,
            formations,
            risk_mode=RiskMode.MATCHUP,
            opponent_samples=opponent_samples,
            initial=decision.lineup,
        )
        assert scored_lineup.score_samples is not None
        differences = scored_lineup.score_samples - opponent_samples
        draws = np.isclose(differences, 0.0, atol=1e-8, rtol=0)
        decision = replace(
            decision,
            lineup=scored_lineup,
            win_probability=float(np.mean((differences > 0) & ~draws)),
            draw_probability=float(np.mean(draws)),
            loss_probability=float(np.mean((differences < 0) & ~draws)),
        )
    except NoLegalLineupError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT) from None
    simulation = await _create_simulation_run(
        session,
        user_bundle,
        league_id,
        rule.version,
        simulation_count=payload.simulation_count,
        seed=payload.seed,
        method="head_to_head_monte_carlo",
        decision=decision.lineup,
    )
    explanations = _lineup_explanations(decision.lineup, user_bundle)
    persisted = await _persist_lineup(
        session,
        simulation.id,
        league_id,
        team.id,
        decision.lineup,
        user_bundle,
        explanations,
    )
    await session.commit()
    return MatchupRecommendationView(
        lineup=_lineup_view(
            persisted.id,
            team.id,
            decision.lineup,
            user_bundle,
            explanations,
        ),
        opponent_fantasy_team_id=opponent.id,
        win_probability=decision.win_probability,
        draw_probability=decision.draw_probability,
        loss_probability=decision.loss_probability,
        simulation_count=payload.simulation_count,
    )


async def _roster_bundle_or_409(
    session: AsyncSession,
    league_id: uuid.UUID,
    fantasy_team_id: uuid.UUID,
    scoring: object,
    simulation_count: int | None = None,
    seed: int = 2026,
    horizon: int = 1,
    decision_cutoff: datetime | None = None,
    prediction_run_id: uuid.UUID | None = None,
) -> ProjectionBundle:
    from markguardiola.fantasy.rules import ScoringRules

    if not isinstance(scoring, ScoringRules):
        raise TypeError()
    try:
        return await load_roster_projection_bundle(
            session,
            league_id=league_id,
            fantasy_team_id=fantasy_team_id,
            rules=scoring,
            simulation_count=simulation_count,
            seed=seed,
            horizon=horizon,
            decision_cutoff=decision_cutoff,
            prediction_run_id=prediction_run_id,
        )
    except PredictionDataUnavailableError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT) from None


async def _create_simulation_run(
    session: AsyncSession,
    bundle: ProjectionBundle,
    league_id: uuid.UUID,
    rule_version: int,
    *,
    simulation_count: int,
    seed: int | None,
    method: str,
    decision: LineupDecision | None = None,
) -> SimulationRun:
    run = SimulationRun(
        prediction_run_id=bundle.prediction_run_id,
        league_id=league_id,
        simulation_count=simulation_count,
        seed=seed,
        scoring_rule_version=rule_version,
        parameters={
            "method": method,
            "prediction_cutoff": bundle.prediction_cutoff.isoformat(),
            "decision_cutoff": bundle.decision_cutoff.isoformat(),
            **(
                {
                    "optimization_method": decision.optimization_method,
                    "evaluated_candidates": decision.evaluated_candidates,
                    "search_scenarios": decision.search_scenarios,
                    "global_optimality_proven": False,
                }
                if decision is not None
                else {}
            ),
        },
        storage_path="database://recommendation",
    )
    session.add(run)
    await session.flush()
    return run


async def _persist_lineup(
    session: AsyncSession,
    simulation_run_id: uuid.UUID,
    league_id: uuid.UUID,
    fantasy_team_id: uuid.UUID,
    decision: LineupDecision,
    bundle: ProjectionBundle,
    explanations: tuple[Explanation, ...],
) -> LineupRecommendation:
    input_by_id = {item.player_id: item for item in bundle.inputs}
    selected_ids = {item.player_id for item in decision.starters}
    samples = [
        sample
        for player_id in selected_ids
        if (sample := input_by_id[player_id].samples) is not None
    ]
    if len(samples) != len(selected_ids):
        raise ValueError()
    median = float(
        np.median(
            decision.score_samples
            if decision.score_samples is not None
            else np.sum(np.stack(samples), axis=0)
        )
    )
    recommendation = LineupRecommendation(
        simulation_run_id=simulation_run_id,
        league_id=league_id,
        fantasy_team_id=fantasy_team_id,
        risk_mode=decision.risk_mode.value,
        formation=decision.formation,
        starters=[
            {
                "player_id": item.player_id,
                "display_name": item.display_name,
                "slot": item.slot,
                "expected_points": item.expected_points,
                "appearance_probability": item.appearance_probability,
            }
            for item in decision.starters
        ],
        bench=[
            {
                "player_id": item.player_id,
                "display_name": item.display_name,
                "roles": item.roles,
                "utility": item.utility,
            }
            for item in decision.bench
        ],
        expected_score=decision.expected_points,
        median_score=median,
        p10_score=decision.p10_points,
        p90_score=decision.p90_points,
        confidence=bundle.confidence,
        objective_value=decision.objective_value,
        data_cutoff=bundle.data_cutoff,
    )
    session.add(recommendation)
    await session.flush()
    await _persist_explanations(session, "lineup", recommendation.id, explanations)
    return recommendation


async def _persist_explanations(
    session: AsyncSession,
    recommendation_type: str,
    recommendation_id: uuid.UUID,
    explanations: tuple[Explanation, ...],
) -> None:
    for rank, explanation in enumerate(explanations, start=1):
        session.add(
            RecommendationExplanation(
                recommendation_type=recommendation_type,
                recommendation_id=recommendation_id,
                rank=rank,
                text=explanation.text,
                evidence_type=explanation.evidence_key,
                evidence={"source_feature": explanation.source_feature},
                confidence=explanation.confidence,
            )
        )


def _lineup_explanations(
    decision: LineupDecision,
    bundle: ProjectionBundle,
) -> tuple[Explanation, ...]:
    high_appearance_count = sum(item.appearance_probability >= 0.8 for item in decision.starters)
    return ExplanationEngine().explain(
        [
            InsightEvidence(
                key="lineup_high_appearance_count",
                value=float(high_appearance_count),
                impact=float(high_appearance_count),
                reliability=bundle.confidence,
                source_feature="selected_players.appearance_probability",
            ),
            InsightEvidence(
                key="lineup_expected_substitutions",
                value=decision.expected_substitutions,
                impact=decision.expected_substitutions,
                reliability=bundle.confidence,
                source_feature="joint_lineup.substitution_counts",
            ),
            InsightEvidence(
                key="lineup_modifier_points",
                value=decision.expected_modifier,
                impact=decision.expected_modifier,
                reliability=bundle.confidence,
                source_feature="joint_lineup.modifier_scores",
            ),
        ],
        overall_confidence=bundle.confidence,
    )


def _lineup_view(
    recommendation_id: uuid.UUID,
    fantasy_team_id: uuid.UUID,
    decision: LineupDecision,
    bundle: ProjectionBundle,
    explanations: tuple[Explanation, ...],
) -> LineupRecommendationView:
    photos = {player.player_id: player.photo_url for player in bundle.inputs}
    return LineupRecommendationView(
        recommendation_id=recommendation_id,
        fantasy_team_id=fantasy_team_id,
        formation=decision.formation,
        risk_mode=decision.risk_mode,
        starters=tuple(
            SelectedPlayerView(
                player_id=uuid.UUID(item.player_id),
                display_name=item.display_name,
                photo_url=photos.get(item.player_id),
                slot=item.slot,
                expected_points=item.expected_points,
                appearance_probability=item.appearance_probability,
            )
            for item in decision.starters
        ),
        bench=tuple(
            BenchPlayerView(
                player_id=uuid.UUID(item.player_id),
                display_name=item.display_name,
                photo_url=photos.get(item.player_id),
                roles=item.roles,
                utility=item.utility,
            )
            for item in decision.bench
        ),
        expected_points=decision.expected_points,
        p10_points=decision.p10_points,
        p90_points=decision.p90_points,
        confidence=bundle.confidence,
        data_cutoff=bundle.data_cutoff,
        explanations=_explanation_views(explanations),
        decision_cutoff=bundle.decision_cutoff,
        expected_substitutions=decision.expected_substitutions,
        expected_modifier=decision.expected_modifier,
        optimization_method=decision.optimization_method,
        evaluated_candidates=decision.evaluated_candidates,
        search_scenarios=decision.search_scenarios,
        warnings=bundle.warnings,
    )


def _explanation_views(explanations: tuple[Explanation, ...]) -> tuple[ExplanationView, ...]:
    return tuple(
        ExplanationView(
            text=item.text,
            evidence_key=item.evidence_key,
            source_feature=item.source_feature,
            confidence=item.confidence,
        )
        for item in explanations
    )


async def _latest_budget(session: AsyncSession, fantasy_team_id: uuid.UUID) -> Budget | None:
    result = await session.execute(
        select(Budget)
        .where(Budget.fantasy_team_id == fantasy_team_id)
        .order_by(Budget.effective_at.desc())
    )
    return result.scalars().first()
