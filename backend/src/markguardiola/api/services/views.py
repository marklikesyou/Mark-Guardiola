from __future__ import annotations

import uuid
from collections.abc import Mapping

from markguardiola.api.contracts import MatchSummary, TeamSummary
from markguardiola.db.models import Match, Team
from markguardiola.domain.enums import KickoffPrecision


def team_summary(team: Team) -> TeamSummary:
    return TeamSummary(
        id=team.id,
        name=team.name,
        short_name=team.short_name,
        country_code=team.country_code,
    )


def match_summary(match: Match, teams: Mapping[uuid.UUID, Team]) -> MatchSummary:
    return MatchSummary(
        id=match.id,
        kickoff_at=match.kickoff_at,
        kickoff_precision=KickoffPrecision(match.kickoff_precision or "unknown"),
        matchweek=match.matchweek,
        status=match.status,
        home_team=team_summary(teams[match.home_team_id]),
        away_team=team_summary(teams[match.away_team_id]),
        home_score=match.home_score,
        away_score=match.away_score,
    )
