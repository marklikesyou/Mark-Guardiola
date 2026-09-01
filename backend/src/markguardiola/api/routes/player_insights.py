from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import AwareDatetime
from sqlalchemy.ext.asyncio import AsyncSession

from markguardiola.api.contracts import (
    PlayerOutlookRequest,
    PlayerOutlookView,
    PlayerRecentFormView,
)
from markguardiola.api.services.context import get_active_rules, get_league
from markguardiola.api.services.fixture_simulations import PredictionDataUnavailableError
from markguardiola.api.services.player_form import load_recent_form
from markguardiola.api.services.player_outlook import load_player_outlook
from markguardiola.db.models import Player
from markguardiola.db.session import get_db_session

router = APIRouter(prefix="/api/v1", tags=["player-insights"])
Session = Annotated[AsyncSession, Depends(get_db_session)]


@router.get(
    "/players/{player_id}/recent-form",
    response_model=PlayerRecentFormView,
    operation_id="getPlayerRecentForm",
)
async def player_recent_form(
    player_id: uuid.UUID,
    session: Session,
    limit: int = Query(default=5, ge=1, le=20),
    as_of: AwareDatetime | None = None,
) -> PlayerRecentFormView:
    now = datetime.now(UTC)
    if as_of is not None and as_of > now:
        raise HTTPException(status_code=422)
    if await session.get(Player, player_id) is None:
        raise HTTPException(status_code=404)
    return await load_recent_form(session, player_id=player_id, as_of=as_of or now, limit=limit)


@router.post(
    "/leagues/{league_id}/players/{player_id}/outlook",
    response_model=PlayerOutlookView,
    operation_id="getPlayerLeagueOutlook",
)
async def player_league_outlook(
    league_id: uuid.UUID,
    player_id: uuid.UUID,
    request: PlayerOutlookRequest,
    session: Session,
) -> PlayerOutlookView:
    await get_league(session, league_id)
    player = await session.get(Player, player_id)
    if player is None:
        raise HTTPException(status_code=404)
    if not player.active:
        raise HTTPException(status_code=409)
    rule = await get_active_rules(session, league_id)
    try:
        return await load_player_outlook(
            session, league_id=league_id, player_id=player_id, rule=rule, horizon=request.horizon
        )
    except PredictionDataUnavailableError:
        raise HTTPException(status_code=409) from None
