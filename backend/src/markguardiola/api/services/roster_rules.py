from __future__ import annotations

import uuid
from collections import defaultdict

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from markguardiola.api.services.imports import ResolvedImport, normalize_fantasy_role
from markguardiola.db.models import FantasyTeam, Player, PlayerFantasyRole, RosterEntry
from markguardiola.domain.roles import football_role
from markguardiola.fantasy.roster import (
    CLASSIC_ROLES,
    MANTRA_ROLES,
    RosterConstraints,
    RosterValidation,
    validate_roster,
)
from markguardiola.fantasy.rules import Formation


def validate_rule_configuration(
    mode: str, formations: tuple[Formation, ...], constraints: RosterConstraints
) -> None:
    allowed = CLASSIC_ROLES if mode == "classic" else MANTRA_ROLES
    if any(set(formation.slots) - allowed for formation in formations):
        raise HTTPException(status_code=422)
    if len({formation.name for formation in formations}) != len(formations):
        raise HTTPException(status_code=422)
    if set(constraints.role_limits) - allowed:
        raise HTTPException(status_code=422)
    if allowed.issubset(constraints.role_limits) and constraints.minimum_players > sum(
        constraints.role_limits.values()
    ):
        raise HTTPException(status_code=422)
    if constraints.maximum_players is not None and constraints.maximum_players < 11:
        raise HTTPException(status_code=422)


async def league_roles(
    session: AsyncSession, league_id: uuid.UUID
) -> dict[uuid.UUID, tuple[str, ...]]:
    rows = (
        await session.execute(
            select(PlayerFantasyRole.player_id, PlayerFantasyRole.role)
            .where(PlayerFantasyRole.league_id == league_id)
            .order_by(
                PlayerFantasyRole.player_id,
                PlayerFantasyRole.is_primary.desc(),
                PlayerFantasyRole.role,
            )
        )
    ).all()
    result: dict[uuid.UUID, list[str]] = defaultdict(list)
    for player_id, role in rows:
        result[player_id].append(role)
    return {player_id: tuple(roles) for player_id, roles in result.items()}


def effective_roles(
    assigned: tuple[str, ...], primary_position: str | None, mode: str
) -> tuple[str, ...]:
    if assigned:
        allowed = CLASSIC_ROLES if mode == "classic" else MANTRA_ROLES
        return tuple(role for role in assigned if role in allowed)
    canonical = football_role(primary_position)
    if mode == "mantra":
        return ("Por",) if canonical == "GK" else ()
    return (canonical,) if canonical else ()


def plan_import_roles(
    resolved: list[ResolvedImport], existing: dict[uuid.UUID, tuple[str, ...]], mode: str
) -> dict[uuid.UUID, tuple[str, ...]]:
    grouped: dict[uuid.UUID, list[ResolvedImport]] = defaultdict(list)
    allowed = CLASSIC_ROLES if mode == "classic" else MANTRA_ROLES
    for item in resolved:
        if item.player is not None:
            grouped[item.player.id].append(item)
    planned = {}
    for player_id, items in grouped.items():
        explicit = [item for item in items if item.source.role is not None]
        if explicit:
            roles = []
            for item in explicit:
                role = normalize_fantasy_role(item.source.role, None)
                if mode == "mantra" and role == "GK":
                    role = "Por"
                if role not in allowed:
                    raise HTTPException(status_code=422)
                if role not in roles:
                    roles.append(role)
            planned[player_id] = tuple(roles)
        else:
            player = items[0].player
            assert player is not None
            planned[player_id] = effective_roles(
                existing.get(player_id, ()), player.primary_position, mode
            )
    return {
        player_id: roles
        for player_id, roles in planned.items()
        if roles != existing.get(player_id, ())
    }


async def load_roster_roles(
    session: AsyncSession, league_id: uuid.UUID, team_id: uuid.UUID, mode: str
) -> dict[str, tuple[str, ...]]:
    assigned = await league_roles(session, league_id)
    players = (
        await session.scalars(
            select(Player)
            .join(RosterEntry, RosterEntry.player_id == Player.id)
            .where(RosterEntry.fantasy_team_id == team_id, RosterEntry.active.is_(True))
        )
    ).all()
    allowed = CLASSIC_ROLES if mode == "classic" else MANTRA_ROLES
    return {
        str(player.id): tuple(
            role
            for role in effective_roles(assigned.get(player.id, ()), player.primary_position, mode)
            if role in allowed
        )
        for player in players
    }


def enforce_roster(validation: RosterValidation) -> None:
    if not validation.valid:
        raise HTTPException(status_code=409)


async def validate_import_state(
    session: AsyncSession,
    *,
    league_id: uuid.UUID,
    mode: str,
    constraints: RosterConstraints,
    current_roles: dict[uuid.UUID, tuple[str, ...]],
    planned_roles: dict[uuid.UUID, tuple[str, ...]],
    team_id: uuid.UUID | None = None,
    imported_players: dict[uuid.UUID, Player] | None = None,
    replace_existing: bool = False,
) -> None:
    rows = (
        await session.execute(
            select(RosterEntry.fantasy_team_id, Player)
            .join(Player, Player.id == RosterEntry.player_id)
            .join(FantasyTeam, FantasyTeam.id == RosterEntry.fantasy_team_id)
            .where(FantasyTeam.league_id == league_id, RosterEntry.active.is_(True))
        )
    ).all()
    rosters: dict[uuid.UUID, dict[uuid.UUID, Player]] = defaultdict(dict)
    affected = {team_id} if team_id is not None else set()
    for roster_id, player in rows:
        rosters[roster_id][player.id] = player
        if player.id in planned_roles:
            affected.add(roster_id)
    if team_id is not None and imported_players is not None:
        if replace_existing:
            rosters[team_id] = {}
        rosters[team_id].update(imported_players)
    merged = {**current_roles, **planned_roles}
    allowed = CLASSIC_ROLES if mode == "classic" else MANTRA_ROLES
    for roster_id in affected:
        players = {
            str(player.id): tuple(
                role
                for role in effective_roles(
                    merged.get(player.id, ()), player.primary_position, mode
                )
                if role in allowed
            )
            for player in rosters[roster_id].values()
        }
        enforce_roster(validate_roster(players, constraints, require_complete=False))


async def persist_import_roles(
    session: AsyncSession,
    league_id: uuid.UUID,
    planned: dict[uuid.UUID, tuple[str, ...]],
    resolved: list[ResolvedImport],
) -> None:
    if not planned:
        return
    await session.execute(
        delete(PlayerFantasyRole).where(
            PlayerFantasyRole.league_id == league_id, PlayerFantasyRole.player_id.in_(planned)
        )
    )
    explicit = {
        item.player.id
        for item in resolved
        if item.player is not None and item.source.role is not None
    }
    session.add_all(
        PlayerFantasyRole(
            league_id=league_id,
            player_id=player_id,
            role=role,
            is_primary=index == 0,
            source="user_import" if player_id in explicit else "canonical",
        )
        for player_id, roles in planned.items()
        for index, role in enumerate(roles)
    )
