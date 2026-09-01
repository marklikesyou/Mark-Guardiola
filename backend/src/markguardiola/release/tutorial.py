from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from markguardiola.api.services.fixture_simulations import PredictionDataUnavailableError
from markguardiola.api.services.prediction_runs import latest_compatible_prediction_run
from markguardiola.core.time import utcnow
from markguardiola.db.models import (
    Budget,
    FantasyTeam,
    League,
    LeagueMember,
    LeagueRule,
    MarketEntry,
    Match,
    Player,
    PlayerFantasyRole,
    PlayerMatchPrediction,
    RosterEntry,
    Season,
    User,
)
from markguardiola.fantasy.roster import RosterConstraints
from markguardiola.fantasy.rules import CLASSIC_FORMATIONS, ScoringRules

TUTORIAL_LEAGUE_NAME = "Tutorial"
TUTORIAL_IDENTITY = "local-owner"
ROLE_QUOTAS = {"GK": 3, "DEF": 8, "MID": 8, "FWD": 6}
MARKET_QUOTAS = {"GK": 5, "DEF": 12, "MID": 12, "FWD": 10}


@dataclass(frozen=True, slots=True)
class TutorialCandidate:
    player_id: uuid.UUID
    display_name: str
    role: str
    expected_minutes: float
    reliability: float


@dataclass(frozen=True, slots=True)
class TutorialDraft:
    user_roster: tuple[TutorialCandidate, ...]
    opponent_roster: tuple[TutorialCandidate, ...]
    market: tuple[TutorialCandidate, ...]


async def provision_tutorial_league(session: AsyncSession) -> dict[str, object]:

    owner = await session.scalar(select(User).where(User.local_identity == TUTORIAL_IDENTITY))
    if owner is not None:
        existing = await session.scalar(
            select(League).where(
                League.owner_user_id == owner.id,
                League.name == TUTORIAL_LEAGUE_NAME,
            )
        )
        if existing is not None:
            return await _summary(session, existing, created=False)

    run = await latest_compatible_prediction_run(session)
    candidates, season = await _prediction_candidates(session, run.id)
    draft = build_tutorial_draft(candidates)

    if owner is None:
        owner = User(display_name="Allenatore", local_identity=TUTORIAL_IDENTITY)
        session.add(owner)
        await session.flush()

    now = utcnow()
    league = League(
        owner_user_id=owner.id,
        name=TUTORIAL_LEAGUE_NAME,
        mode="classic",
        competition_id=season.competition_id,
        season_id=season.id,
        head_to_head_enabled=True,
        timezone="Europe/Rome",
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

    user_team = FantasyTeam(
        league_id=league.id,
        member_id=member.id,
        name="Rosa Tutorial",
        is_user_team=True,
    )
    opponent_team = FantasyTeam(
        league_id=league.id,
        name="Avversaria Tutorial",
        is_user_team=False,
    )
    session.add_all([user_team, opponent_team])
    await session.flush()

    session.add(
        LeagueRule(
            league_id=league.id,
            version=1,
            effective_from=now,
            scoring=ScoringRules().model_dump(mode="json"),
            formations=[formation.model_dump(mode="json") for formation in CLASSIC_FORMATIONS],
            roster_constraints=RosterConstraints(role_limits=ROLE_QUOTAS).model_dump(mode="json"),
            substitution_rules={"bench_size": 7, "maximum_substitutions": 5},
            active=True,
        )
    )
    session.add_all(
        [
            Budget(
                fantasy_team_id=team.id,
                effective_at=now,
                total_credits=Decimal("500"),
                remaining_credits=Decimal("500"),
            )
            for team in (user_team, opponent_team)
        ]
    )

    roles: dict[uuid.UUID, str] = {}
    for team, roster in (
        (user_team, draft.user_roster),
        (opponent_team, draft.opponent_roster),
    ):
        for candidate in roster:
            roles[candidate.player_id] = candidate.role
            session.add(
                RosterEntry(
                    fantasy_team_id=team.id,
                    player_id=candidate.player_id,
                    acquired_at=now,
                    purchase_price=None,
                    imported_name=None,
                    active=True,
                )
            )
    for candidate in draft.market:
        roles[candidate.player_id] = candidate.role
        session.add(
            MarketEntry(
                league_id=league.id,
                player_id=candidate.player_id,
                available=True,
                asking_price=None,
                imported_name=None,
            )
        )
    session.add_all(
        PlayerFantasyRole(
            league_id=league.id,
            player_id=player_id,
            role=role,
            is_primary=True,
            source="current_prediction",
        )
        for player_id, role in roles.items()
    )
    await session.flush()
    return await _summary(session, league, created=True)


def build_tutorial_draft(candidates: list[TutorialCandidate]) -> TutorialDraft:

    grouped = {
        role: sorted(
            (candidate for candidate in candidates if candidate.role == role),
            key=lambda item: (
                -item.expected_minutes,
                -item.reliability,
                item.display_name.casefold(),
                str(item.player_id),
            ),
        )
        for role in ROLE_QUOTAS
    }
    user: list[TutorialCandidate] = []
    opponent: list[TutorialCandidate] = []
    market: list[TutorialCandidate] = []
    for role, roster_quota in ROLE_QUOTAS.items():
        required = roster_quota * 2 + MARKET_QUOTAS[role]
        if len(grouped[role]) < required:
            raise PredictionDataUnavailableError()
        roster_pool = grouped[role][: roster_quota * 2]
        user.extend(roster_pool[::2])
        opponent.extend(roster_pool[1::2])
        market.extend(grouped[role][roster_quota * 2 : required])
    return TutorialDraft(tuple(user), tuple(opponent), tuple(market))


async def _prediction_candidates(
    session: AsyncSession, run_id: uuid.UUID
) -> tuple[list[TutorialCandidate], Season]:
    rows = (
        await session.execute(
            select(
                Player,
                PlayerMatchPrediction.expected_value,
                PlayerMatchPrediction.reliability,
                PlayerMatchPrediction.distribution,
                Match.season_id,
            )
            .join(PlayerMatchPrediction, PlayerMatchPrediction.player_id == Player.id)
            .join(Match, Match.id == PlayerMatchPrediction.match_id)
            .where(
                PlayerMatchPrediction.prediction_run_id == run_id,
                PlayerMatchPrediction.target == "expected_minutes",
                Player.active.is_(True),
                Match.kickoff_at > utcnow(),
                Match.status.not_in(["finished", "cancelled", "abandoned", "awarded"]),
            )
            .order_by(Match.kickoff_at, Player.display_name, Player.id)
        )
    ).all()
    candidates: dict[uuid.UUID, TutorialCandidate] = {}
    season_id: uuid.UUID | None = None
    for player, expected_minutes, reliability, distribution, row_season_id in rows:
        role = distribution.get("football_role") if isinstance(distribution, dict) else None
        if player.id in candidates or role not in ROLE_QUOTAS:
            continue
        season_id = season_id or row_season_id
        candidates[player.id] = TutorialCandidate(
            player_id=player.id,
            display_name=player.display_name,
            role=role,
            expected_minutes=float(expected_minutes),
            reliability=float(reliability),
        )
    if season_id is None:
        raise PredictionDataUnavailableError()
    season = await session.get(Season, season_id)
    if season is None:
        raise PredictionDataUnavailableError()
    return list(candidates.values()), season


async def _summary(session: AsyncSession, league: League, *, created: bool) -> dict[str, object]:
    teams = list(
        (
            await session.scalars(
                select(FantasyTeam)
                .where(FantasyTeam.league_id == league.id)
                .order_by(FantasyTeam.is_user_team.desc(), FantasyTeam.name)
            )
        ).all()
    )
    roster_counts = {
        team.name: len(
            list(
                (
                    await session.scalars(
                        select(RosterEntry).where(
                            RosterEntry.fantasy_team_id == team.id,
                            RosterEntry.active.is_(True),
                        )
                    )
                ).all()
            )
        )
        for team in teams
    }
    market_count = len(
        list(
            (
                await session.scalars(
                    select(MarketEntry).where(
                        MarketEntry.league_id == league.id,
                        MarketEntry.available.is_(True),
                    )
                )
            ).all()
        )
    )
    return {
        "created": created,
        "league_id": str(league.id),
        "name": league.name,
        "rosters": roster_counts,
        "market_players": market_count,
    }
