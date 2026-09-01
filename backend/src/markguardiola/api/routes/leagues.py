from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from markguardiola.api.contracts import (
    BudgetView,
    BudgetWrite,
    FantasyTeamView,
    ImportResult,
    LeagueCreate,
    LeaguePage,
    LeagueRulesView,
    LeagueRulesWrite,
    LeagueSettingsWrite,
    LeagueSummary,
    LeagueView,
    MarketImportRequest,
    PageMeta,
    RosterImportRequest,
    RosterPlayerView,
    RosterView,
)
from markguardiola.api.services.context import get_active_rules, get_fantasy_team, get_league
from markguardiola.api.services.imports import ResolvedImport, resolve_imported_players
from markguardiola.api.services.roster_rules import (
    effective_roles,
    league_roles,
    persist_import_roles,
    plan_import_roles,
    validate_import_state,
    validate_rule_configuration,
)
from markguardiola.core.time import utcnow
from markguardiola.db.models import (
    Budget,
    FantasyTeam,
    League,
    LeagueMember,
    LeagueRule,
    MarketEntry,
    Player,
    PlayerFantasyRole,
    RosterEntry,
    User,
)
from markguardiola.db.session import get_db_session
from markguardiola.domain.enums import LeagueMode
from markguardiola.fantasy.roster import RosterConstraints, validate_roster
from markguardiola.fantasy.rules import (
    CLASSIC_FORMATIONS,
    DEFAULT_MANTRA_FORMATIONS,
    Formation,
    ScoringRules,
)
from markguardiola.fantasy.rules.models import SubstitutionRules

router = APIRouter(prefix="/api/v1/leagues", tags=["leagues"])
Session = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("", response_model=LeaguePage, operation_id="listLeagues")
async def list_leagues(
    session: Session,
    local_identity: str = Query(default="local-owner", min_length=1, max_length=160),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> LeaguePage:
    statement = (
        select(League)
        .join(User, User.id == League.owner_user_id)
        .where(User.local_identity == local_identity)
    )
    total = await session.scalar(select(func.count()).select_from(statement.subquery()))
    leagues = await session.scalars(
        statement.order_by(League.created_at.desc(), League.id).offset(offset).limit(limit)
    )
    return LeaguePage(
        items=[LeagueSummary.model_validate(row) for row in leagues],
        meta=PageMeta(limit=limit, offset=offset, total=total or 0),
    )


@router.post("", response_model=LeagueView, status_code=201, operation_id="createLeague")
async def create_league(payload: LeagueCreate, session: Session) -> LeagueView:
    owner = await session.scalar(select(User).where(User.local_identity == payload.local_identity))
    if owner is None:
        owner = User(
            display_name=payload.owner_display_name,
            local_identity=payload.local_identity,
        )
        session.add(owner)
        await session.flush()
    league = League(
        owner_user_id=owner.id,
        name=payload.name,
        mode=payload.mode.value,
        competition_id=payload.competition_id,
        season_id=payload.season_id,
        head_to_head_enabled=payload.head_to_head_enabled,
        timezone=payload.timezone,
    )
    session.add(league)
    await session.flush()
    member = LeagueMember(
        league_id=league.id,
        user_id=owner.id,
        display_name=owner.display_name,
        is_owner=True,
    )
    session.add(member)
    await session.flush()
    fantasy_team = FantasyTeam(
        league_id=league.id,
        member_id=member.id,
        name=payload.team_name,
        is_user_team=True,
    )
    session.add(fantasy_team)
    await session.flush()
    scoring = ScoringRules()
    formations = _default_formations(payload.mode)
    session.add(
        LeagueRule(
            league_id=league.id,
            version=1,
            effective_from=utcnow(),
            scoring=scoring.model_dump(mode="json"),
            formations=[formation.model_dump(mode="json") for formation in formations],
            roster_constraints=_default_roster_constraints(payload.mode).model_dump(mode="json"),
            substitution_rules={"bench_size": 7, "maximum_substitutions": 5},
            active=True,
        )
    )
    session.add(
        Budget(
            fantasy_team_id=fantasy_team.id,
            effective_at=utcnow(),
            total_credits=payload.total_credits,
            remaining_credits=payload.total_credits,
        )
    )
    await session.commit()
    return await _league_view(session, league.id)


@router.get("/{league_id}", response_model=LeagueView, operation_id="getLeague")
async def read_league(league_id: uuid.UUID, session: Session) -> LeagueView:
    return await _league_view(session, league_id)


@router.patch("/{league_id}", response_model=LeagueView, operation_id="updateLeagueSettings")
async def update_league_settings(
    league_id: uuid.UUID,
    payload: LeagueSettingsWrite,
    session: Session,
) -> LeagueView:
    league = await get_league(session, league_id)
    if payload.name is not None:
        league.name = payload.name
    if payload.head_to_head_enabled is not None:
        league.head_to_head_enabled = payload.head_to_head_enabled
    await session.commit()
    return await _league_view(session, league.id)


@router.put(
    "/{league_id}/teams/{fantasy_team_id}/budget",
    response_model=BudgetView,
    operation_id="updateFantasyTeamBudget",
)
async def update_budget(
    league_id: uuid.UUID,
    fantasy_team_id: uuid.UUID,
    payload: BudgetWrite,
    session: Session,
) -> BudgetView:
    team = await get_fantasy_team(session, league_id, fantasy_team_id, user_team_default=False)
    previous = await _latest_budget(session, team.id)
    budget = Budget(
        fantasy_team_id=team.id,
        effective_at=utcnow(),
        total_credits=previous.total_credits if previous else payload.remaining_credits,
        remaining_credits=payload.remaining_credits,
    )
    session.add(budget)
    await session.commit()
    return BudgetView.model_validate(budget)


@router.put(
    "/{league_id}/rules",
    response_model=LeagueRulesView,
    operation_id="replaceLeagueRules",
)
async def replace_league_rules(
    league_id: uuid.UUID,
    payload: LeagueRulesWrite,
    session: Session,
) -> LeagueRulesView:
    league = await get_league(session, league_id, lock=True)
    current = await get_active_rules(session, league_id)
    formations = payload.formations or _default_formations(LeagueMode(league.mode))
    validate_rule_configuration(league.mode, formations, payload.roster_constraints)
    await session.execute(
        update(LeagueRule).where(LeagueRule.league_id == league_id).values(active=False)
    )
    replacement = LeagueRule(
        league_id=league_id,
        version=current.version + 1,
        effective_from=utcnow(),
        scoring=payload.scoring.model_dump(mode="json"),
        formations=[formation.model_dump(mode="json") for formation in formations],
        roster_constraints=payload.roster_constraints.model_dump(mode="json"),
        substitution_rules=payload.substitution_rules.model_dump(mode="json"),
        active=True,
    )
    session.add(replacement)
    await session.commit()
    return _rules_view(replacement)


@router.post(
    "/{league_id}/rosters/import",
    response_model=ImportResult,
    operation_id="importRoster",
)
async def import_roster(
    league_id: uuid.UUID,
    payload: RosterImportRequest,
    session: Session,
) -> ImportResult:
    league = await get_league(session, league_id, lock=True)
    rule = await get_active_rules(session, league_id)
    fantasy_team: FantasyTeam | None
    if payload.fantasy_team_id is not None:
        fantasy_team = await get_fantasy_team(
            session, league_id, payload.fantasy_team_id, user_team_default=False
        )
    else:
        fantasy_team = await session.scalar(
            select(FantasyTeam).where(
                FantasyTeam.league_id == league_id,
                FantasyTeam.name == payload.fantasy_team_name,
            )
        )
        if fantasy_team is None:
            fantasy_team = FantasyTeam(
                id=uuid.uuid4(),
                league_id=league_id,
                name=payload.fantasy_team_name,
                is_user_team=payload.is_user_team,
            )
    assert fantasy_team is not None

    resolved = await resolve_imported_players(session, payload.players)
    current_roles = await league_roles(session, league_id)
    planned_roles = plan_import_roles(resolved, current_roles, league.mode)
    unique = _unique_priced_imports(resolved)
    await validate_import_state(
        session,
        league_id=league_id,
        mode=league.mode,
        constraints=RosterConstraints.model_validate(rule.roster_constraints),
        current_roles=current_roles,
        planned_roles=planned_roles,
        team_id=fantasy_team.id,
        imported_players={
            item.player.id: item.player for item in resolved if item.player is not None
        },
        replace_existing=payload.replace_existing,
    )
    session.add(fantasy_team)
    await session.flush()
    if payload.replace_existing:
        await session.execute(
            update(RosterEntry)
            .where(RosterEntry.fantasy_team_id == fantasy_team.id)
            .values(active=False, released_at=utcnow())
        )
    existing = {
        entry.player_id: entry
        for entry in (
            await session.scalars(
                select(RosterEntry).where(RosterEntry.fantasy_team_id == fantasy_team.id)
            )
        ).all()
    }
    for item in unique:
        if item.player is None:
            continue
        entry = existing.get(item.player.id)
        if entry is None:
            entry = RosterEntry(
                fantasy_team_id=fantasy_team.id,
                player_id=item.player.id,
                acquired_at=utcnow(),
                purchase_price=item.source.purchase_price,
                imported_name=item.source.name,
                active=True,
            )
            session.add(entry)
            existing[item.player.id] = entry
        else:
            entry.active = True
            entry.released_at = None
            entry.imported_name = item.source.name
            if payload.replace_existing or "purchase_price" in item.source.model_fields_set:
                entry.purchase_price = item.source.purchase_price
    await persist_import_roles(session, league_id, planned_roles, resolved)
    if payload.remaining_credits is not None:
        latest_budget = await _latest_budget(session, fantasy_team.id)
        session.add(
            Budget(
                fantasy_team_id=fantasy_team.id,
                effective_at=utcnow(),
                total_credits=(
                    latest_budget.total_credits
                    if latest_budget is not None
                    else payload.remaining_credits
                ),
                remaining_credits=payload.remaining_credits,
            )
        )
    await session.commit()
    resolutions = [item.resolution for item in resolved]
    return ImportResult(
        fantasy_team_id=fantasy_team.id,
        resolved_count=sum(item.status == "resolved" for item in resolutions),
        unresolved_count=sum(item.status != "resolved" for item in resolutions),
        resolutions=resolutions,
    )


@router.get(
    "/{league_id}/rosters",
    response_model=list[RosterView],
    operation_id="listLeagueRosters",
)
async def list_rosters(league_id: uuid.UUID, session: Session) -> list[RosterView]:
    league = await get_league(session, league_id)
    rule = await get_active_rules(session, league_id)
    fantasy_teams = list(
        (
            await session.scalars(
                select(FantasyTeam)
                .where(FantasyTeam.league_id == league_id)
                .order_by(FantasyTeam.is_user_team.desc(), FantasyTeam.name)
            )
        ).all()
    )
    output: list[RosterView] = []
    for fantasy_team in fantasy_teams:
        rows = (
            await session.execute(
                select(RosterEntry, Player)
                .join(Player, Player.id == RosterEntry.player_id)
                .where(
                    RosterEntry.fantasy_team_id == fantasy_team.id,
                    RosterEntry.active.is_(True),
                )
                .order_by(Player.display_name)
            )
        ).all()
        player_ids = [player.id for _entry, player in rows]
        role_rows = (
            await session.execute(
                select(PlayerFantasyRole.player_id, PlayerFantasyRole.role)
                .where(
                    PlayerFantasyRole.league_id == league_id,
                    PlayerFantasyRole.player_id.in_(player_ids),
                )
                .order_by(PlayerFantasyRole.is_primary.desc(), PlayerFantasyRole.role)
            )
        ).all()
        roles: dict[uuid.UUID, list[str]] = {}
        for player_id, role in role_rows:
            roles.setdefault(player_id, []).append(role)
        budget = await _latest_budget(session, fantasy_team.id)
        output.append(
            RosterView(
                validation=validate_roster(
                    {
                        str(player.id): effective_roles(
                            tuple(roles.get(player.id, [])), player.primary_position, league.mode
                        )
                        for _, player in rows
                    },
                    RosterConstraints.model_validate(rule.roster_constraints),
                ),
                fantasy_team=FantasyTeamView(
                    id=fantasy_team.id,
                    name=fantasy_team.name,
                    is_user_team=fantasy_team.is_user_team,
                    remaining_credits=(budget.remaining_credits if budget is not None else None),
                ),
                players=[
                    RosterPlayerView(
                        player_id=player.id,
                        display_name=player.display_name,
                        photo_url=player.photo_url,
                        roles=tuple(roles.get(player.id, [])),
                        primary_position=player.primary_position,
                        purchase_price=entry.purchase_price,
                        active=entry.active,
                    )
                    for entry, player in rows
                ],
            )
        )
    return output


@router.post(
    "/{league_id}/market/import",
    response_model=ImportResult,
    operation_id="importMarket",
)
async def import_market(
    league_id: uuid.UUID,
    payload: MarketImportRequest,
    session: Session,
) -> ImportResult:
    league = await get_league(session, league_id, lock=True)
    rule = await get_active_rules(session, league_id)
    resolved = await resolve_imported_players(session, payload.players)
    current_roles = await league_roles(session, league_id)
    planned_roles = plan_import_roles(resolved, current_roles, league.mode)
    unique = _unique_priced_imports(resolved)
    await validate_import_state(
        session,
        league_id=league_id,
        mode=league.mode,
        constraints=RosterConstraints.model_validate(rule.roster_constraints),
        current_roles=current_roles,
        planned_roles=planned_roles,
    )
    if payload.replace_existing:
        await session.execute(
            update(MarketEntry).where(MarketEntry.league_id == league_id).values(available=False)
        )
    existing = {
        entry.player_id: entry
        for entry in (
            await session.scalars(select(MarketEntry).where(MarketEntry.league_id == league_id))
        ).all()
    }
    for item in unique:
        if item.player is None:
            continue
        entry = existing.get(item.player.id)
        if entry is None:
            entry = MarketEntry(
                league_id=league_id,
                player_id=item.player.id,
                available=True,
                asking_price=item.source.purchase_price,
                imported_name=item.source.name,
            )
            session.add(entry)
        else:
            entry.available = True
            if payload.replace_existing or "purchase_price" in item.source.model_fields_set:
                entry.asking_price = item.source.purchase_price
            entry.imported_name = item.source.name
    await persist_import_roles(session, league_id, planned_roles, resolved)
    await session.commit()
    resolutions = [item.resolution for item in resolved]
    return ImportResult(
        resolved_count=sum(item.status == "resolved" for item in resolutions),
        unresolved_count=sum(item.status != "resolved" for item in resolutions),
        resolutions=resolutions,
    )


async def _league_view(session: AsyncSession, league_id: uuid.UUID) -> LeagueView:
    league = await get_league(session, league_id)
    rules = await get_active_rules(session, league_id)
    teams = list(
        (
            await session.scalars(
                select(FantasyTeam)
                .where(FantasyTeam.league_id == league_id)
                .order_by(FantasyTeam.is_user_team.desc(), FantasyTeam.name)
            )
        ).all()
    )
    team_views = []
    for team in teams:
        budget = await _latest_budget(session, team.id)
        team_views.append(
            FantasyTeamView(
                id=team.id,
                name=team.name,
                is_user_team=team.is_user_team,
                remaining_credits=(budget.remaining_credits if budget is not None else None),
            )
        )
    return LeagueView(
        id=league.id,
        name=league.name,
        mode=LeagueMode(league.mode),
        owner_user_id=league.owner_user_id,
        competition_id=league.competition_id,
        season_id=league.season_id,
        head_to_head_enabled=league.head_to_head_enabled,
        timezone=league.timezone,
        rules=_rules_view(rules),
        fantasy_teams=team_views,
    )


def _rules_view(rules: LeagueRule) -> LeagueRulesView:
    return LeagueRulesView(
        version=rules.version,
        effective_from=rules.effective_from,
        scoring=ScoringRules.model_validate(rules.scoring),
        formations=tuple(Formation.model_validate(item) for item in rules.formations),
        roster_constraints=RosterConstraints.model_validate(rules.roster_constraints),
        substitution_rules=SubstitutionRules.model_validate(rules.substitution_rules),
    )


async def _latest_budget(
    session: AsyncSession,
    fantasy_team_id: uuid.UUID,
) -> Budget | None:
    result = await session.execute(
        select(Budget)
        .where(Budget.fantasy_team_id == fantasy_team_id)
        .order_by(Budget.effective_at.desc())
    )
    return result.scalars().first()


def _default_formations(mode: LeagueMode) -> tuple[Formation, ...]:
    return CLASSIC_FORMATIONS if mode == LeagueMode.CLASSIC else DEFAULT_MANTRA_FORMATIONS


def _default_roster_constraints(mode: LeagueMode) -> RosterConstraints:
    if mode == LeagueMode.CLASSIC:
        return RosterConstraints(role_limits={"GK": 3, "DEF": 8, "MID": 8, "FWD": 6})
    return RosterConstraints(minimum_players=23, maximum_players=30)


def _unique_priced_imports(resolved: list[ResolvedImport]) -> list[ResolvedImport]:
    prices: dict[uuid.UUID, Decimal | None] = {}
    unique: dict[uuid.UUID, ResolvedImport] = {}
    for item in resolved:
        if item.player is None:
            continue
        unique.setdefault(item.player.id, item)
        if item.player is not None and "purchase_price" in item.source.model_fields_set:
            player_id = item.player.id
            if player_id in prices and prices[player_id] != item.source.purchase_price:
                raise HTTPException(status_code=422)
            prices[player_id] = item.source.purchase_price
            unique[player_id] = item
    return list(unique.values())
