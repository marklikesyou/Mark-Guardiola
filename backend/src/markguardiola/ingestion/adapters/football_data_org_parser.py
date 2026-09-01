from datetime import datetime

from markguardiola.ingestion.adapters.http import json_payload
from markguardiola.ingestion.contracts import CanonicalMatchRecord, RawPayload
from markguardiola.ingestion.contracts.operational import (
    OperationalBatch,
    StandingObservation,
    TeamIdentity,
)


def parse_football_data_org(payload: RawPayload) -> OperationalBatch:
    body = json_payload(payload)
    if body.get("errorCode") or (
        body.get("message")
        and "matches" not in body
        and "standings" not in body
        and "teams" not in body
    ):
        raise ValueError()
    endpoint = (payload.schema_hint or "").removeprefix("football-data-org-v4:")
    observed = payload.retrieved_at
    snapshot = observed.isoformat()
    batch = OperationalBatch()
    if endpoint == "matches":
        for row in body["matches"]:
            if row["competition"]["code"] != "SA":
                raise ValueError()
            year = int(row["season"]["startDate"][:4])
            referee = next(
                (item for item in row.get("referees", []) if item.get("type") == "REFEREE"), None
            )
            score = row["score"].get("fullTime") or {}
            batch.matches.append(
                CanonicalMatchRecord(
                    source_record_id=str(row["id"]),
                    season_label=f"{year}-{year + 1}",
                    competition_name="Serie A",
                    kickoff_at=datetime.fromisoformat(row["utcDate"]),
                    available_at=observed,
                    kickoff_precision="date" if row["status"] == "SCHEDULED" else "minute",
                    home_team_provider_id=str(row["homeTeam"]["id"]),
                    home_team_name=row["homeTeam"].get("shortName") or row["homeTeam"]["name"],
                    away_team_provider_id=str(row["awayTeam"]["id"]),
                    away_team_name=row["awayTeam"].get("shortName") or row["awayTeam"]["name"],
                    status={"TIMED": "scheduled", "IN_PLAY": "live", "PAUSED": "live"}.get(
                        row["status"], row["status"].lower()
                    ),
                    home_score=score.get("home") if row["status"] == "FINISHED" else None,
                    away_score=score.get("away") if row["status"] == "FINISHED" else None,
                    matchweek=row.get("matchday"),
                    snapshot_key=snapshot,
                    referee_provider_id=str(referee["id"]) if referee else None,
                    referee_name=referee["name"] if referee else None,
                )
            )
    elif endpoint == "standings":
        year = int(body["season"]["startDate"][:4])
        for group in body["standings"]:
            for row in group["table"]:
                batch.standings.append(
                    StandingObservation(
                        source_record_id=f"{year}:{row['team']['id']}:{group['type']}:{snapshot}",
                        event_time=observed,
                        available_at=observed,
                        season_label=f"{year}-{year + 1}",
                        team=TeamIdentity(
                            provider_id=str(row["team"]["id"]),
                            name=row["team"].get("shortName") or row["team"]["name"],
                        ),
                        table_type=group["type"],
                        rank=row["position"],
                        played=row["playedGames"],
                        points=row["points"],
                        won=row["won"],
                        drawn=row["draw"],
                        lost=row["lost"],
                        goals_for=row["goalsFor"],
                        goals_against=row["goalsAgainst"],
                    )
                )
    elif endpoint == "teams":
        for row in body["teams"]:
            batch.teams.append(
                TeamIdentity(provider_id=str(row["id"]), name=row.get("shortName") or row["name"])
            )
    else:
        raise ValueError()
    return batch
