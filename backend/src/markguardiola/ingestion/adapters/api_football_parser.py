from __future__ import annotations

from datetime import date, datetime
from typing import Any

from markguardiola.ingestion.adapters.http import json_payload
from markguardiola.ingestion.contracts import (
    CanonicalMatchRecord,
    CanonicalPlayerMatchRecord,
    RawPayload,
)
from markguardiola.ingestion.contracts.base import (
    CanonicalEventRecord,
    CanonicalLineupRecord,
    CanonicalPlayerIdentity,
)
from markguardiola.ingestion.contracts.operational import (
    AvailabilityObservation,
    OddsObservation,
    OperationalBatch,
    StandingObservation,
    TeamIdentity,
    TransferObservation,
)

_STATUS = {
    "TBD": "scheduled",
    "NS": "scheduled",
    "FT": "finished",
    "AET": "finished",
    "PEN": "finished",
    "PST": "postponed",
    "CANC": "cancelled",
    "ABD": "abandoned",
    "AWD": "awarded",
    "WO": "forfeited",
    "SUSP": "suspended",
    "1H": "live",
    "HT": "live",
    "2H": "live",
    "ET": "live",
    "BT": "live",
    "P": "live",
    "INT": "suspended",
    "LIVE": "live",
}
_TEAM_STATS = {
    "Shots on Goal": "shots_on_target",
    "Shots off Goal": "shots_off_target",
    "Total Shots": "shots",
    "Blocked Shots": "blocked_shots",
    "Fouls": "fouls",
    "Corner Kicks": "corners",
    "Offsides": "offsides",
    "Ball Possession": "possession",
    "Yellow Cards": "yellow_cards",
    "Red Cards": "red_cards",
    "Goalkeeper Saves": "saves",
    "Total passes": "passes",
    "Passes accurate": "accurate_passes",
    "expected_goals": "xg",
}
_PLAYER_STATS = {
    "goals": ("goals", "total"),
    "assists": ("goals", "assists"),
    "saves": ("goals", "saves"),
    "goals_conceded": ("goals", "conceded"),
    "shots": ("shots", "total"),
    "shots_on_target": ("shots", "on"),
    "yellow_cards": ("cards", "yellow"),
    "red_cards": ("cards", "red"),
    "tackles": ("tackles", "total"),
    "interceptions": ("tackles", "interceptions"),
    "blocks": ("tackles", "blocks"),
    "key_passes": ("passes", "key"),
    "fouls": ("fouls", "committed"),
    "penalties_scored": ("penalty", "scored"),
    "penalties_missed": ("penalty", "missed"),
    "penalties_saved": ("penalty", "saved"),
    "penalties_won": ("penalty", "won"),
    "rating": ("games", "rating"),
}


def parse_api_football(payload: RawPayload) -> OperationalBatch:
    body = json_payload(payload)
    if body.get("errors"):
        raise ValueError()
    rows = body.get("response")
    if not isinstance(rows, list):
        raise ValueError()
    endpoint = (payload.schema_hint or "").removeprefix("api-football-v3:")
    batch = OperationalBatch()
    observed = payload.retrieved_at
    snapshot = observed.isoformat()
    for row in rows:
        if endpoint == "fixtures":
            _fixture(batch, row, observed, snapshot)
        elif endpoint == "teams":
            batch.teams.append(_team(row["team"]))
        elif endpoint == "players":
            player = _player(row["player"], observed)
            statistics = row.get("statistics") or []
            if statistics:
                player = player.model_copy(
                    update={"position": (statistics[-1].get("games") or {}).get("position")}
                )
                for statistic in statistics:
                    if statistic.get("team", {}).get("id"):
                        batch.teams.append(_team(statistic["team"]))
            batch.players.append(player)
        elif endpoint == "injuries":
            _injury(batch, row, observed, snapshot)
        elif endpoint == "standings":
            _standings(batch, row, observed, snapshot)
        elif endpoint == "transfers":
            batch.players.append(_player(row["player"], observed))
            for index, transfer in enumerate(row.get("transfers") or []):
                day = date.fromisoformat(transfer["date"])
                teams = transfer["teams"]
                batch.transfers.append(
                    TransferObservation(
                        source_record_id=f"transfer:{row['player']['id']}:{day}:{index}:{snapshot}",
                        event_time=datetime.combine(
                            day, datetime.min.time(), tzinfo=observed.tzinfo
                        ),
                        available_at=observed,
                        player_provider_id=str(row["player"]["id"]),
                        from_team=_team(teams["out"]) if teams.get("out", {}).get("id") else None,
                        to_team=_team(teams["in"]) if teams.get("in", {}).get("id") else None,
                        transfer_date=day,
                        transfer_type=transfer.get("type"),
                    )
                )
        elif endpoint == "odds":
            _odds(batch, row, observed, snapshot)
        else:
            raise ValueError()
    return batch


def _team(row: dict[str, Any]) -> TeamIdentity:
    return TeamIdentity(provider_id=str(row["id"]), name=row["name"])


def _player(
    row: dict[str, Any], observed: datetime, match_id: str | None = None
) -> CanonicalPlayerIdentity:
    birth = (row.get("birth") or {}).get("date")
    return CanonicalPlayerIdentity(
        player_provider_id=str(row["id"]),
        player_name=row["name"],
        available_at=observed,
        match_provider_id=match_id,
        position=row.get("pos"),
        date_of_birth=date.fromisoformat(birth) if birth else None,
        given_name=row.get("firstname"),
        family_name=row.get("lastname"),
        photo_url=row.get("photo"),
    )


def _number(value: object) -> float | None:
    if value is None:
        return None
    return float(str(value).removesuffix("%"))


def _fixture(
    batch: OperationalBatch, row: dict[str, Any], observed: datetime, snapshot: str
) -> None:
    fixture, league, teams = row["fixture"], row["league"], row["teams"]
    if int(league["id"]) != 135:
        raise ValueError()
    match_id, kickoff = str(fixture["id"]), datetime.fromisoformat(fixture["date"])
    status = _STATUS[fixture["status"]["short"]]
    year = int(league["season"])
    round_name = str(league.get("round") or "")
    matchweek = (
        int(round_name.rsplit(" - ", 1)[-1]) if round_name.rsplit(" - ", 1)[-1].isdigit() else None
    )
    venue = fixture.get("venue") or {}
    stats: dict[str, int | float | str | None] = {}
    if status == "finished":
        for group in row.get("statistics") or []:
            team_id = group["team"]["id"]
            side = next((side for side, team in teams.items() if team["id"] == team_id), None)
            if side is None:
                raise ValueError()
            for item in group.get("statistics") or []:
                key = _TEAM_STATS.get(item["type"])
                if key:
                    stats[f"{side}_{key}"] = _number(item.get("value"))
    goals = row.get("goals") or {}
    batch.matches.append(
        CanonicalMatchRecord(
            source_record_id=match_id,
            season_label=f"{year}-{year + 1}",
            competition_name="Serie A",
            kickoff_at=kickoff,
            kickoff_precision="date" if fixture["status"]["short"] == "TBD" else "minute",
            available_at=observed,
            home_team_provider_id=str(teams["home"]["id"]),
            home_team_name=teams["home"]["name"],
            away_team_provider_id=str(teams["away"]["id"]),
            away_team_name=teams["away"]["name"],
            status=status,
            matchweek=matchweek,
            home_score=goals.get("home") if status == "finished" else None,
            away_score=goals.get("away") if status == "finished" else None,
            referee_name=fixture.get("referee"),
            venue_name=venue.get("name"),
            venue_city=venue.get("city"),
            venue_provider_id=str(venue["id"]) if venue.get("id") else None,
            snapshot_key=snapshot,
            stats=stats,
        )
    )
    starters: set[str] = set()
    for group in row.get("lineups") or []:
        for label, starting in (("startXI", True), ("substitutes", False)):
            for entry in group.get(label) or []:
                player = entry["player"]
                batch.players.append(_player(player, observed, match_id))
                if starting:
                    starters.add(str(player["id"]))
                batch.lineups.append(
                    CanonicalLineupRecord(
                        source_record_id=f"{match_id}:lineup:{player['id']}:{snapshot}",
                        match_provider_id=match_id,
                        team_provider_id=str(group["team"]["id"]),
                        player_provider_id=str(player["id"]),
                        is_starting=starting,
                        shirt_number=player.get("number"),
                        position=player.get("pos"),
                        formation_slot=player.get("grid"),
                        available_at=observed,
                    )
                )
    for group in row.get("players") or []:
        for entry in group.get("players") or []:
            player = entry["player"]
            batch.players.append(_player(player, observed, match_id))
            if status != "finished":
                continue
            for statistic in entry.get("statistics") or []:
                games = statistic.get("games") or {}
                if games.get("minutes") is None:
                    continue
                values = {
                    key: _number((statistic.get(section) or {}).get(field))
                    for key, (section, field) in _PLAYER_STATS.items()
                }

                values["own_goals"] = None
                values["event_statistics_available"] = int(
                    all(values[key] is not None for key in ("goals", "yellow_cards", "red_cards"))
                )

                if str(player["id"]) not in starters and games.get("substitute") is None:
                    continue
                batch.player_stats.append(
                    CanonicalPlayerMatchRecord(
                        source_record_id=f"{match_id}:player:{player['id']}:{snapshot}",
                        match_provider_id=match_id,
                        player_provider_id=str(player["id"]),
                        player_name=player["name"],
                        team_provider_id=str(group["team"]["id"]),
                        team_name=group["team"]["name"],
                        event_time=kickoff,
                        available_at=observed,
                        minutes=games["minutes"],
                        started=str(player["id"]) in starters or games.get("substitute") is False,
                        position=games.get("position"),
                        stats=values,
                    )
                )
    for index, event in enumerate(row.get("events") or []):
        player = event.get("player") or {}
        if player.get("id") and player.get("name"):
            batch.players.append(_player(player, observed, match_id))
        time = event.get("time") or {}
        minute = int(time.get("elapsed") or 0) + int(time.get("extra") or 0)
        batch.events.append(
            CanonicalEventRecord(
                source_record_id=f"{match_id}:event:{index}:{snapshot}",
                match_provider_id=match_id,
                team_provider_id=str(event["team"]["id"]),
                player_provider_id=str(player["id"])
                if player.get("id") and player.get("name")
                else None,
                event_type=event["type"],
                event_subtype=event.get("detail"),
                second=minute * 60,
                available_at=observed,
                detail={"comments": event.get("comments"), "assist": event.get("assist")},
            )
        )


def _injury(
    batch: OperationalBatch, row: dict[str, Any], observed: datetime, snapshot: str
) -> None:
    player, team, fixture = row["player"], row["team"], row["fixture"]
    kickoff = datetime.fromisoformat(fixture["date"])
    batch.players.append(_player(player, observed, str(fixture["id"])))
    batch.teams.append(_team(team))
    reason = player.get("reason")
    suspended = bool(reason and "suspend" in reason.casefold())

    batch.availability.append(
        AvailabilityObservation(
            source_record_id=f"{fixture['id']}:absence:{player['id']}:{snapshot}",
            event_time=kickoff,
            available_at=observed,
            player_provider_id=str(player["id"]),
            team_provider_id=str(team["id"]),
            reason=reason,
            status="out" if player.get("type") == "Missing Fixture" else "doubtful",
            suspended=suspended,
            starts_on=kickoff.date(),
            ends_on=kickoff.date(),
        )
    )


def _standings(
    batch: OperationalBatch, row: dict[str, Any], observed: datetime, snapshot: str
) -> None:
    league = row["league"]
    year = int(league["season"])
    for table in league.get("standings") or []:
        for item in table:
            total = item["all"]
            batch.standings.append(
                StandingObservation(
                    source_record_id=f"{year}:{item['team']['id']}:TOTAL:{snapshot}",
                    event_time=observed,
                    available_at=observed,
                    team=_team(item["team"]),
                    season_label=f"{year}-{year + 1}",
                    rank=item["rank"],
                    points=item["points"],
                    played=total["played"],
                    won=total["win"],
                    drawn=total["draw"],
                    lost=total["lose"],
                    goals_for=total["goals"]["for"],
                    goals_against=total["goals"]["against"],
                )
            )


def _odds(batch: OperationalBatch, row: dict[str, Any], observed: datetime, snapshot: str) -> None:
    fixture = row["fixture"]
    kickoff = datetime.fromisoformat(fixture["date"])
    for bookmaker in row.get("bookmakers") or []:
        for bet in bookmaker.get("bets") or []:
            for value in bet.get("values") or []:
                if value.get("odd") is None:
                    continue
                batch.odds.append(
                    OddsObservation(
                        source_record_id=f"{fixture['id']}:{bookmaker['id']}:{bet['id']}:{value['value']}:{snapshot}",
                        event_time=kickoff,
                        available_at=observed,
                        match_provider_id=str(fixture["id"]),
                        bookmaker=bookmaker["name"],
                        market=bet["name"],
                        selection=str(value["value"]),
                        decimal_odds=float(value["odd"]),
                    )
                )
