from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from markguardiola.db.base import Base
from markguardiola.db.models import Match, ProviderEntityMap, Team
from markguardiola.domain.enums import EntityType
from markguardiola.entity_resolution.normalization import normalize_name


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    team_redirects: dict[uuid.UUID, uuid.UUID]
    match_redirects: dict[uuid.UUID, uuid.UUID]


async def reconcile_identities(
    session: AsyncSession, *, apply: bool = False
) -> ReconciliationResult:
    teams = list((await session.scalars(select(Team).order_by(Team.created_at, Team.id))).all())
    team_groups: dict[tuple[str | None, str], list[Team]] = defaultdict(list)
    for team in teams:
        team_groups[(team.country_code, normalize_name(team.name, entity_type="team"))].append(team)
    team_redirects = {
        duplicate.id: group[0].id for group in team_groups.values() for duplicate in group[1:]
    }
    matches = list(
        (await session.scalars(select(Match).order_by(Match.created_at, Match.id))).all()
    )
    owners: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for mapping in (
        await session.scalars(
            select(ProviderEntityMap).where(ProviderEntityMap.entity_type == EntityType.MATCH)
        )
    ).all():
        owners[mapping.canonical_entity_id].add(mapping.source_id)
    pairs: dict[tuple[uuid.UUID, uuid.UUID, uuid.UUID], list[Match]] = defaultdict(list)
    for match in matches:
        pairs[
            (
                match.season_id,
                team_redirects.get(match.home_team_id, match.home_team_id),
                team_redirects.get(match.away_team_id, match.away_team_id),
            )
        ].append(match)
    corroborated_dates: dict[uuid.UUID, date] = {}
    for pair in pairs.values():
        if len(pair) != 2:
            continue
        first, second = pair
        if (
            owners[first.id]
            and owners[second.id]
            and not owners[first.id].intersection(owners[second.id])
            and first.home_score is not None
            and first.away_score is not None
            and (first.home_score, first.away_score) == (second.home_score, second.away_score)
            and abs((first.kickoff_at - second.kickoff_at).total_seconds()) <= 21 * 86400
        ):
            corroborated_dates[second.id] = first.kickoff_at.date()
    match_groups: dict[tuple[uuid.UUID, uuid.UUID, uuid.UUID, date], list[Match]] = defaultdict(
        list
    )
    for match in matches:
        home = team_redirects.get(match.home_team_id, match.home_team_id)
        away = team_redirects.get(match.away_team_id, match.away_team_id)
        if home == away:
            raise ValueError()
        identity_date = corroborated_dates.get(match.id, match.kickoff_at.date())
        match_groups[(match.season_id, home, away, identity_date)].append(match)
    match_redirects: dict[uuid.UUID, uuid.UUID] = {}
    for group in match_groups.values():
        scores = {
            (match.home_score, match.away_score)
            for match in group
            if match.home_score is not None and match.away_score is not None
        }

        awarded = any(match.status in {"awarded", "forfeited"} for match in group)
        if len(scores) > 1 and not awarded:
            raise ValueError()
        keeper = group[0]
        for duplicate in group[1:]:
            match_redirects[duplicate.id] = keeper.id
        if apply and len(group) > 1:
            complete = next((match for match in group if match.home_score is not None), keeper)
            keeper.home_score = complete.home_score
            keeper.away_score = complete.away_score
            keeper.status = "awarded" if awarded else complete.status
            keeper.available_at = max(match.available_at for match in group)

    result = ReconciliationResult(team_redirects, match_redirects)
    if not apply:
        return result
    await session.flush()

    await _redirect(session, "matches", EntityType.MATCH, match_redirects)
    await _redirect(session, "teams", EntityType.TEAM, team_redirects)
    for (_country, normalized), team_group in team_groups.items():
        await session.execute(
            update(Team).where(Team.id == team_group[0].id).values(normalized_name=normalized)
        )
    await session.flush()
    return result


async def _redirect(
    session: AsyncSession,
    table_name: str,
    entity_type: EntityType,
    redirects: dict[uuid.UUID, uuid.UUID],
) -> None:
    target_table = Base.metadata.tables[table_name]
    for old_id, canonical_id in redirects.items():
        for table in Base.metadata.tables.values():
            for column in table.columns:
                if any(fk.column.table is target_table for fk in column.foreign_keys):
                    await session.execute(
                        update(table).where(column == old_id).values({column.name: canonical_id})
                    )
        await session.execute(
            update(ProviderEntityMap)
            .where(
                ProviderEntityMap.entity_type == entity_type,
                ProviderEntityMap.canonical_entity_id == old_id,
            )
            .values(canonical_entity_id=canonical_id)
        )
        await session.execute(delete(target_table).where(target_table.c.id == old_id))
