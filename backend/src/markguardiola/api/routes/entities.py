from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from markguardiola.api.contracts import (
    MatchPage,
    PageMeta,
    PlayerDetail,
    PlayerPage,
    PlayerSummary,
    TeamPage,
)
from markguardiola.api.services.views import match_summary, team_summary
from markguardiola.db.models import Match, Player, PlayerTeamPeriod, Team
from markguardiola.db.session import get_db_session

router = APIRouter(prefix="/api/v1", tags=["football"])
Session = Annotated[AsyncSession, Depends(get_db_session)]


def _photo_source(player: Player) -> str | None:
    source = player.photo_provenance.get("source")
    return source if isinstance(source, str) else None


def _player_summary(player: Player) -> PlayerSummary:
    return PlayerSummary(
        id=player.id,
        display_name=player.display_name,
        primary_position=player.primary_position,
        nationality_code=player.nationality_code,
        photo_url=player.photo_url,
        photo_source=_photo_source(player),
        active=player.active,
    )


@router.get("/players", response_model=PlayerPage, operation_id="listPlayers")
async def list_players(
    session: Session,
    search: str | None = Query(default=None, max_length=200),
    position: str | None = Query(default=None, max_length=32),
    active: bool | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> PlayerPage:
    filters = []
    if search:
        filters.append(Player.display_name.ilike(f"%{search}%"))
    if position:
        filters.append(Player.primary_position.ilike(position))
    if active is not None:
        filters.append(Player.active.is_(active))
    total = await session.scalar(select(func.count(Player.id)).where(*filters)) or 0
    players = list(
        (
            await session.scalars(
                select(Player)
                .where(*filters)
                .order_by(Player.display_name, Player.id)
                .offset(offset)
                .limit(limit)
            )
        ).all()
    )
    return PlayerPage(
        items=[_player_summary(player) for player in players],
        meta=PageMeta(limit=limit, offset=offset, total=total),
    )


@router.get("/players/{player_id}", response_model=PlayerDetail, operation_id="getPlayer")
async def get_player(player_id: uuid.UUID, session: Session) -> PlayerDetail:
    player = await session.get(Player, player_id)
    if player is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    today = datetime.now(UTC).date()
    period = await session.scalar(
        select(PlayerTeamPeriod)
        .where(
            PlayerTeamPeriod.player_id == player_id,
            PlayerTeamPeriod.valid_from <= today,
            or_(PlayerTeamPeriod.valid_to.is_(None), PlayerTeamPeriod.valid_to >= today),
        )
        .order_by(PlayerTeamPeriod.valid_from.desc())
        .limit(1)
    )
    current_team = await session.get(Team, period.team_id) if period is not None else None
    return PlayerDetail(
        id=player.id,
        display_name=player.display_name,
        primary_position=player.primary_position,
        nationality_code=player.nationality_code,
        photo_url=player.photo_url,
        photo_source=_photo_source(player),
        active=player.active,
        date_of_birth=player.date_of_birth,
        preferred_foot=player.preferred_foot,
        height_cm=player.height_cm,
        current_team=team_summary(current_team) if current_team is not None else None,
    )


@router.get("/teams", response_model=TeamPage, operation_id="listTeams")
async def list_teams(
    session: Session,
    search: str | None = Query(default=None, max_length=160),
    active: bool | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> TeamPage:
    filters = []
    if search:
        filters.append(Team.name.ilike(f"%{search}%"))
    if active is not None:
        filters.append(Team.active.is_(active))
    total = await session.scalar(select(func.count(Team.id)).where(*filters)) or 0
    teams = list(
        (
            await session.scalars(
                select(Team)
                .where(*filters)
                .order_by(Team.name, Team.id)
                .offset(offset)
                .limit(limit)
            )
        ).all()
    )
    return TeamPage(
        items=[team_summary(team) for team in teams],
        meta=PageMeta(limit=limit, offset=offset, total=total),
    )


@router.get("/matches", response_model=MatchPage, operation_id="listMatches")
async def list_matches(
    session: Session,
    team_id: uuid.UUID | None = None,
    status_filter: str | None = Query(default=None, alias="status", max_length=32),
    from_at: datetime | None = None,
    to_at: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> MatchPage:
    filters = []
    if team_id:
        filters.append(or_(Match.home_team_id == team_id, Match.away_team_id == team_id))
    if status_filter:
        filters.append(Match.status == status_filter)
    if from_at:
        filters.append(Match.kickoff_at >= from_at)
    if to_at:
        filters.append(Match.kickoff_at <= to_at)
    return await _match_page(session, filters, limit, offset)


@router.get(
    "/fixtures/upcoming",
    response_model=MatchPage,
    operation_id="listUpcomingFixtures",
)
async def upcoming_fixtures(
    session: Session,
    team_id: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> MatchPage:
    filters = [Match.kickoff_at >= datetime.now(UTC)]
    if team_id:
        filters.append(or_(Match.home_team_id == team_id, Match.away_team_id == team_id))
    return await _match_page(session, filters, limit, offset)


async def _match_page(
    session: AsyncSession,
    filters: Sequence[ColumnElement[bool]],
    limit: int,
    offset: int,
) -> MatchPage:
    total = await session.scalar(select(func.count(Match.id)).where(*filters)) or 0
    matches = list(
        (
            await session.scalars(
                select(Match)
                .where(*filters)
                .order_by(Match.kickoff_at, Match.id)
                .offset(offset)
                .limit(limit)
            )
        ).all()
    )
    team_ids = {item for match in matches for item in (match.home_team_id, match.away_team_id)}
    teams = {
        team.id: team
        for team in (await session.scalars(select(Team).where(Team.id.in_(team_ids)))).all()
    }
    return MatchPage(
        items=[match_summary(match, teams) for match in matches],
        meta=PageMeta(limit=limit, offset=offset, total=total),
    )
