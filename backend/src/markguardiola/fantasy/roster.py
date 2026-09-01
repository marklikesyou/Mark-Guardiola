from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CLASSIC_ROLES = frozenset({"GK", "DEF", "MID", "FWD"})
MANTRA_ROLES = frozenset({"Por", "Dd", "Ds", "Dc", "B", "E", "M", "C", "T", "W", "A", "Pc"})
Capacity = Annotated[int, Field(strict=True, ge=0, le=500)]


class RosterConstraints(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    minimum_players: Capacity = 0
    maximum_players: Annotated[int, Field(strict=True, ge=1, le=500)] | None = None
    role_limits: dict[str, Capacity] = Field(default_factory=dict)

    @model_validator(mode="after")
    def consistent_limits(self) -> RosterConstraints:
        if self.maximum_players is not None and self.minimum_players > self.maximum_players:
            raise ValueError()
        if set(self.role_limits) - (CLASSIC_ROLES | MANTRA_ROLES):
            raise ValueError()
        return self


class RosterIssue(BaseModel):
    code: Literal["minimum_players", "maximum_players", "role_limits", "missing_roles"]
    message: str


class RosterValidation(BaseModel):
    valid: bool
    player_count: int
    issues: tuple[RosterIssue, ...]


def validate_roster(
    players: Mapping[str, tuple[str, ...]],
    constraints: RosterConstraints,
    *,
    require_complete: bool = True,
) -> RosterValidation:

    issues = []
    count = len(players)
    if require_complete and count < constraints.minimum_players:
        issues.append(
            RosterIssue(
                code="minimum_players",
                message=(
                    f"Rosa incompleta: {count} giocatori, "
                    f"minimo richiesto {constraints.minimum_players}."
                ),
            )
        )
    if constraints.maximum_players is not None and count > constraints.maximum_players:
        issues.append(
            RosterIssue(
                code="maximum_players",
                message=(
                    f"Rosa troppo numerosa: {count} giocatori, "
                    f"massimo consentito {constraints.maximum_players}."
                ),
            )
        )
    known = {
        player: tuple(sorted(set(roles) & (CLASSIC_ROLES | MANTRA_ROLES)))
        for player, roles in players.items()
    }
    missing = sum(not roles for roles in known.values())
    if require_complete and missing:
        issues.append(
            RosterIssue(
                code="missing_roles",
                message=(f"Conferma i ruoli di {missing} giocatori prima di richiedere consigli."),
            )
        )
    if constraints.role_limits and not _fits_role_capacities(
        {player: roles for player, roles in known.items() if roles}, constraints.role_limits
    ):
        issues.append(
            RosterIssue(
                code="role_limits",
                message=(
                    "I giocatori non possono essere assegnati ai posti per ruolo "
                    "consentiti dalla lega."
                ),
            )
        )
    return RosterValidation(valid=not issues, player_count=count, issues=tuple(issues))


def _fits_role_capacities(
    players: Mapping[str, tuple[str, ...]], limits: Mapping[str, int]
) -> bool:
    occupants: dict[str, list[str]] = {}

    def place(player: str, visited: set[str]) -> bool:
        for role in players[player]:
            if role in visited:
                continue
            visited.add(role)
            assigned = occupants.setdefault(role, [])
            if len(assigned) < limits.get(role, len(players)):
                assigned.append(player)
                return True
            for index, previous in enumerate(assigned):
                if place(previous, visited):
                    assigned[index] = player
                    return True
        return False

    return all(
        place(player, set()) for player in sorted(players, key=lambda p: (len(players[p]), p))
    )
