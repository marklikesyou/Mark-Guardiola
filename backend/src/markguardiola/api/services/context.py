from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from markguardiola.db.models import FantasyTeam, League, LeagueRule
from markguardiola.fantasy.rules import Formation, ScoringRules


async def get_league(session: AsyncSession, league_id: uuid.UUID, *, lock: bool = False) -> League:
    league = (
        await session.scalar(select(League).where(League.id == league_id).with_for_update())
        if lock
        else await session.get(League, league_id)
    )
    if league is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return league


async def get_active_rules(session: AsyncSession, league_id: uuid.UUID) -> LeagueRule:
    rules = await session.scalar(
        select(LeagueRule)
        .where(LeagueRule.league_id == league_id, LeagueRule.active.is_(True))
        .order_by(LeagueRule.version.desc())
        .limit(1)
    )
    if rules is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT)
    return rules


async def get_fantasy_team(
    session: AsyncSession,
    league_id: uuid.UUID,
    fantasy_team_id: uuid.UUID | None,
    *,
    user_team_default: bool = True,
) -> FantasyTeam:
    query = select(FantasyTeam).where(FantasyTeam.league_id == league_id)
    if fantasy_team_id is not None:
        query = query.where(FantasyTeam.id == fantasy_team_id)
    elif user_team_default:
        query = query.where(FantasyTeam.is_user_team.is_(True))
    team = await session.scalar(query.order_by(FantasyTeam.created_at).limit(1))
    if team is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return team


def parse_scoring_rules(rule: LeagueRule) -> ScoringRules:
    return ScoringRules.model_validate(rule.scoring)


def parse_formations(rule: LeagueRule) -> tuple[Formation, ...]:
    return tuple(Formation.model_validate(item) for item in rule.formations)
