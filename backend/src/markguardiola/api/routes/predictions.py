from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from markguardiola.api.contracts import (
    FixturePrediction,
    PlayerFixturePrediction,
    PredictionValue,
)
from markguardiola.api.services.fixture_simulations import PredictionDataUnavailableError
from markguardiola.api.services.prediction_runs import latest_compatible_prediction_run
from markguardiola.api.services.views import match_summary
from markguardiola.db.models import (
    Match,
    Player,
    PlayerMatchPrediction,
    PredictionRun,
    Team,
)
from markguardiola.db.session import get_db_session

router = APIRouter(prefix="/api/v1/predictions", tags=["predictions"])
Session = Annotated[AsyncSession, Depends(get_db_session)]


@router.get(
    "/player/{player_id}",
    response_model=list[PlayerFixturePrediction],
    operation_id="getPlayerPredictions",
)
async def player_predictions(
    player_id: uuid.UUID,
    session: Session,
) -> list[PlayerFixturePrediction]:
    if await session.get(Player, player_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    run = await _latest_run(session)
    rows = (
        await session.execute(
            select(PlayerMatchPrediction, Match)
            .join(Match, Match.id == PlayerMatchPrediction.match_id)
            .where(
                PlayerMatchPrediction.prediction_run_id == run.id,
                PlayerMatchPrediction.player_id == player_id,
            )
            .order_by(Match.kickoff_at, PlayerMatchPrediction.target)
        )
    ).all()
    grouped: dict[uuid.UUID, tuple[Match, list[PlayerMatchPrediction]]] = {}
    for prediction, match in rows:
        grouped.setdefault(match.id, (match, []))[1].append(prediction)
    return [
        await _player_fixture_view(session, run, player_id, match, values)
        for match, values in grouped.values()
    ]


@router.get(
    "/fixture/{match_id}",
    response_model=FixturePrediction,
    operation_id="getFixturePredictions",
)
async def fixture_predictions(match_id: uuid.UUID, session: Session) -> FixturePrediction:
    match = await session.get(Match, match_id)
    if match is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    run = await _latest_run(session)
    predictions = list(
        (
            await session.scalars(
                select(PlayerMatchPrediction)
                .where(
                    PlayerMatchPrediction.prediction_run_id == run.id,
                    PlayerMatchPrediction.match_id == match_id,
                )
                .order_by(PlayerMatchPrediction.player_id, PlayerMatchPrediction.target)
            )
        ).all()
    )
    grouped: dict[uuid.UUID, list[PlayerMatchPrediction]] = {}
    for prediction in predictions:
        grouped.setdefault(prediction.player_id, []).append(prediction)
    teams = await _teams_for_match(session, match)
    return FixturePrediction(
        match=match_summary(match, teams),
        prediction_run_id=run.id,
        prediction_cutoff=run.prediction_cutoff,
        data_cutoff=run.data_cutoff,
        players=[
            PlayerFixturePrediction(
                player_id=player_id,
                prediction_run_id=run.id,
                match=match_summary(match, teams),
                prediction_cutoff=run.prediction_cutoff,
                data_cutoff=run.data_cutoff,
                values=[_prediction_value(value, run) for value in values],
            )
            for player_id, values in grouped.items()
        ],
    )


async def _latest_run(session: AsyncSession) -> PredictionRun:
    try:
        return await latest_compatible_prediction_run(session)
    except PredictionDataUnavailableError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT) from None


async def _player_fixture_view(
    session: AsyncSession,
    run: PredictionRun,
    player_id: uuid.UUID,
    match: Match,
    predictions: list[PlayerMatchPrediction],
) -> PlayerFixturePrediction:
    teams = await _teams_for_match(session, match)
    return PlayerFixturePrediction(
        player_id=player_id,
        prediction_run_id=run.id,
        match=match_summary(match, teams),
        prediction_cutoff=run.prediction_cutoff,
        data_cutoff=run.data_cutoff,
        values=[_prediction_value(value, run) for value in predictions],
    )


async def _teams_for_match(session: AsyncSession, match: Match) -> dict[uuid.UUID, Team]:
    teams = list(
        (
            await session.scalars(
                select(Team).where(Team.id.in_([match.home_team_id, match.away_team_id]))
            )
        ).all()
    )
    return {team.id: team for team in teams}


def _prediction_value(prediction: PlayerMatchPrediction, run: PredictionRun) -> PredictionValue:
    return PredictionValue(
        target=prediction.target,
        model_version=run.model_versions[prediction.target],
        expected_value=prediction.expected_value,
        median=prediction.median,
        p10=prediction.p10,
        p90=prediction.p90,
        probability=prediction.probability,
        reliability=prediction.reliability,
    )
