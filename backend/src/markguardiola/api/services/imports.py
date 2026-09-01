from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from markguardiola.api.contracts import (
    ImportPlayer,
    ImportResolutionView,
    ResolutionCandidateView,
)
from markguardiola.db.models import Player, PlayerTeamPeriod, Team
from markguardiola.domain.roles import football_role
from markguardiola.entity_resolution import (
    EntityResolver,
    IdentityCandidate,
    IdentityQuery,
    ResolutionStatus,
)
from markguardiola.entity_resolution.normalization import normalize_name


@dataclass(frozen=True, slots=True)
class ResolvedImport:
    source: ImportPlayer
    player: Player | None
    resolution: ImportResolutionView


async def resolve_imported_players(
    session: AsyncSession,
    rows: list[ImportPlayer],
) -> list[ResolvedImport]:
    players = list((await session.scalars(select(Player).where(Player.active.is_(True)))).all())
    players_by_id = {player.id: player for player in players}
    teams = list((await session.scalars(select(Team))).all())
    teams_by_name = {normalize_name(team.name): team.id for team in teams}
    periods = list((await session.scalars(select(PlayerTeamPeriod))).all())
    latest_period: dict[uuid.UUID, PlayerTeamPeriod] = {}
    for period in periods:
        previous = latest_period.get(period.player_id)
        if previous is None or period.valid_from > previous.valid_from:
            latest_period[period.player_id] = period

    candidates = [
        IdentityCandidate(
            canonical_id=player.id,
            name=player.display_name,
            date_of_birth=player.date_of_birth,
            nationality_code=player.nationality_code,
            team_id=(latest_period[player.id].team_id if player.id in latest_period else None),
            position=(
                latest_period[player.id].position
                if player.id in latest_period
                else player.primary_position
            ),
            team_valid_from=(
                latest_period[player.id].valid_from if player.id in latest_period else None
            ),
            team_valid_to=(
                latest_period[player.id].valid_to if player.id in latest_period else None
            ),
        )
        for player in players
    ]
    resolver = EntityResolver()
    output: list[ResolvedImport] = []
    for row in rows:
        if row.player_id is not None:
            selected = players_by_id.get(row.player_id)
            if selected is None:
                output.append(_unknown_explicit_player(row))
                continue
            output.append(
                ResolvedImport(
                    source=row,
                    player=selected,
                    resolution=ImportResolutionView(
                        imported_name=row.name,
                        status="resolved",
                        selected_player_id=selected.id,
                        confidence=1.0,
                        candidates=(),
                    ),
                )
            )
            continue

        result = resolver.resolve(
            IdentityQuery(
                name=row.name,
                team_id=teams_by_name.get(normalize_name(row.team)) if row.team else None,
                position=row.role,
            ),
            candidates,
        )
        selected_player = (
            players_by_id[result.selected.canonical_id] if result.selected is not None else None
        )
        output.append(
            ResolvedImport(
                source=row,
                player=selected_player,
                resolution=ImportResolutionView(
                    imported_name=row.name,
                    status=_resolution_status(result.status),
                    selected_player_id=(
                        result.selected.canonical_id if result.selected is not None else None
                    ),
                    confidence=result.confidence,
                    candidates=tuple(
                        ResolutionCandidateView(
                            player_id=candidate.candidate.canonical_id,
                            display_name=candidate.candidate.name,
                            photo_url=players_by_id[candidate.candidate.canonical_id].photo_url,
                            confidence=candidate.confidence,
                            evidence=candidate.evidence,
                        )
                        for candidate in result.candidates
                    ),
                ),
            )
        )
    return output


def normalize_fantasy_role(role: str | None, primary_position: str | None) -> str | None:
    if role is None:
        return football_role(primary_position)
    value = (role or primary_position or "").strip()
    if not value:
        return None
    normalized = normalize_name(value).replace(" ", "")
    aliases = {
        "gk": "GK",
        "goalkeeper": "GK",
        "portiere": "GK",
        "por": "Por",
        "def": "DEF",
        "defender": "DEF",
        "difensore": "DEF",
        "mid": "MID",
        "midfielder": "MID",
        "centrocampista": "MID",
        "fwd": "FWD",
        "forward": "FWD",
        "attaccante": "FWD",
    }
    return aliases.get(normalized, football_role(value) or value)


def _unknown_explicit_player(row: ImportPlayer) -> ResolvedImport:
    return ResolvedImport(
        source=row,
        player=None,
        resolution=ImportResolutionView(
            imported_name=row.name,
            status="unresolved",
            selected_player_id=None,
            confidence=0.0,
            candidates=(),
        ),
    )


def _resolution_status(
    status: ResolutionStatus,
) -> str:
    return status.value
