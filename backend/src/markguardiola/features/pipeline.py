from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import polars as pl
import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from markguardiola.core.config import Settings
from markguardiola.db.models import (
    FeatureSnapshotMetadata,
    Match,
    Player,
    PlayerMatchStat,
    Season,
    TeamMatchStat,
)
from markguardiola.domain.roles import football_role
from markguardiola.domain.timing import historical_result_available_at, kickoff_lower_bound
from markguardiola.features.builders import PointInTimeSnapshotBuilder
from markguardiola.features.materialize import materialize_snapshot
from markguardiola.features.membership import resolve_upcoming_memberships
from markguardiola.features.registry import FeatureRegistry
from markguardiola.features.shot_xg import ShotXg, covered_xg, load_shot_xg

FEATURE_SCHEMA_VERSION = "2.1.0"
logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class PreparedSnapshot:
    metadata: FeatureSnapshotMetadata
    frame: pl.DataFrame


@dataclass(frozen=True, slots=True)
class CanonicalHistory:
    player_history: pl.DataFrame
    team_history: pl.DataFrame
    training_candidates: pl.DataFrame
    labels: pl.DataFrame
    latest_team_players: dict[uuid.UUID, list[tuple[uuid.UUID, str]]]
    ingestion_run_ids: tuple[str, ...]
    latest_membership: dict[uuid.UUID, tuple[datetime, uuid.UUID, str]]
    membership_available_at: dict[uuid.UUID, datetime]


async def build_training_snapshot(
    session: AsyncSession,
    settings: Settings,
    *,
    as_of: datetime | None = None,
) -> PreparedSnapshot:
    history = await load_canonical_history(session, cutoff=as_of, completed_seasons_only=True)
    logger.info("training_snapshot_assembling", rows=history.training_candidates.height)
    frame = PointInTimeSnapshotBuilder().build(
        candidates=history.training_candidates,
        player_history=history.player_history,
        team_history=history.team_history,
    )
    frame = frame.join(history.labels, on="snapshot_row_id", how="left")
    return await _persist_snapshot(
        session,
        settings,
        frame,
        history.ingestion_run_ids,
        kind="training",
    )


async def build_upcoming_snapshot(
    session: AsyncSession,
    settings: Settings,
    *,
    cutoff: datetime | None = None,
    horizon_days: int = 90,
) -> PreparedSnapshot:
    prediction_cutoff = cutoff or datetime.now(UTC)
    history = await load_canonical_history(session, cutoff=prediction_cutoff)
    upcoming = list(
        (
            await session.scalars(
                select(Match)
                .where(
                    Match.kickoff_at > prediction_cutoff,
                    Match.available_at <= prediction_cutoff,
                    Match.kickoff_at <= prediction_cutoff + timedelta(days=horizon_days),
                    Match.status.not_in(["finished", "cancelled", "abandoned"]),
                )
                .order_by(Match.kickoff_at)
            )
        ).all()
    )
    memberships = await resolve_upcoming_memberships(
        session,
        upcoming,
        prediction_cutoff,
        history.latest_membership,
        history.membership_available_at,
    )
    candidates: list[dict[str, object]] = []
    for match in upcoming:
        for team_id, opponent_id, home_flag in (
            (match.home_team_id, match.away_team_id, 1),
            (match.away_team_id, match.home_team_id, 0),
        ):
            for player_id, role in memberships.by_fixture_team.get((match.id, team_id), []):
                candidates.append(
                    {
                        "snapshot_row_id": f"{match.id}:{player_id}",
                        "player_id": str(player_id),
                        "team_id": str(team_id),
                        "opponent_team_id": str(opponent_id),
                        "match_id": str(match.id),
                        "prediction_cutoff": prediction_cutoff,
                        "kickoff_at": match.kickoff_at,
                        "home_flag": home_flag,
                        "referee_id": _known_referee(match, prediction_cutoff),
                        "football_role": role,
                        "membership_max_available_at": memberships.available_at[
                            (match.id, player_id)
                        ],
                    }
                )
    if not candidates:
        raise ValueError()
    frame = PointInTimeSnapshotBuilder().build(
        candidates=pl.DataFrame(candidates),
        player_history=history.player_history,
        team_history=history.team_history,
    )
    return await _persist_snapshot(
        session,
        settings,
        frame,
        tuple(sorted(set(history.ingestion_run_ids) | set(memberships.ingestion_run_ids))),
        kind="prediction",
    )


async def load_canonical_history(
    session: AsyncSession,
    *,
    cutoff: datetime | None = None,
    completed_seasons_only: bool = False,
) -> CanonicalHistory:
    version_order = (
        PlayerMatchStat.event_time,
        PlayerMatchStat.available_at,
        PlayerMatchStat.id,
    )

    group_order = [
        func.first_value(column).over(
            partition_by=(PlayerMatchStat.player_id, PlayerMatchStat.match_id),
            order_by=version_order,
        )
        for column in version_order
    ]
    statement = (
        select(PlayerMatchStat, Match, Season.label)
        .join(Match, Match.id == PlayerMatchStat.match_id)
        .join(Season, Season.id == Match.season_id)
        .join(Player, Player.id == PlayerMatchStat.player_id)
        .where(Match.status == "finished")
        .order_by(*group_order, *version_order)
        .options(
            load_only(
                PlayerMatchStat.player_id,
                PlayerMatchStat.match_id,
                PlayerMatchStat.team_id,
                PlayerMatchStat.source_id,
                PlayerMatchStat.ingestion_run_id,
                PlayerMatchStat.event_time,
                PlayerMatchStat.available_at,
                PlayerMatchStat.football_position,
                PlayerMatchStat.minutes,
                PlayerMatchStat.started,
                PlayerMatchStat.stats,
                raiseload=True,
            ),
            load_only(
                Match.home_team_id,
                Match.away_team_id,
                Match.home_score,
                Match.away_score,
                Match.kickoff_at,
                Match.kickoff_precision,
                Match.referee_id,
                Match.referee_available_at,
                raiseload=True,
            ),
        )
    )
    if cutoff is not None:
        statement = statement.where(
            PlayerMatchStat.event_time < cutoff, PlayerMatchStat.available_at <= cutoff
        )
    if completed_seasons_only:
        statement = statement.where(Season.end_date < (cutoff or datetime.now(UTC)).date())
    player_records: list[dict[str, object]] = []
    candidates: list[dict[str, object]] = []
    labels: list[dict[str, object]] = []
    latest_membership: dict[uuid.UUID, tuple[datetime, uuid.UUID, str]] = {}
    membership_available_at: dict[uuid.UUID, datetime] = {}
    known_roles: dict[uuid.UUID, str] = {}
    shot_xg, ingestion_ids = await load_shot_xg(session, cutoff)

    def append_player_match(group: list[tuple[PlayerMatchStat, Match, str]]) -> None:

        stat, match, season_label = group[-1]
        if stat.team_id not in {match.home_team_id, match.away_team_id}:
            return
        is_home = stat.team_id == match.home_team_id
        opponent_id = match.away_team_id if is_home else match.home_team_id
        observed_role = football_role(stat.football_position)
        if observed_role is not None:
            known_roles[stat.player_id] = observed_role
        role = known_roles.get(stat.player_id, "UNKNOWN")
        versions = [item[0] for item in group]
        player_records.extend(_player_history_versions(versions, match, shot_xg))
        row_id = f"{match.id}:{stat.player_id}"
        candidates.append(
            {
                "snapshot_row_id": row_id,
                "player_id": str(stat.player_id),
                "team_id": str(stat.team_id),
                "opponent_team_id": str(opponent_id),
                "match_id": str(match.id),
                "prediction_cutoff": kickoff_lower_bound(match.kickoff_at, match.kickoff_precision),
                "kickoff_at": match.kickoff_at,
                "home_flag": int(is_home),
                "referee_id": _known_referee(
                    match, kickoff_lower_bound(match.kickoff_at, match.kickoff_precision)
                ),
            }
        )
        labels.append(_labels(row_id, stat, match, season_label, role, is_home))
        prior = latest_membership.get(stat.player_id)
        if prior is None or stat.event_time > prior[0]:
            latest_membership[stat.player_id] = (stat.event_time, stat.team_id, role)
            membership_available_at[stat.player_id] = stat.available_at
        ingestion_ids.update(str(version.ingestion_run_id) for version in versions)

    rows = await session.stream(statement.execution_options(yield_per=256))
    group: list[tuple[PlayerMatchStat, Match, str]] = []
    row_count = 0
    try:
        async for stat, match, season_label in rows:
            if group and (stat.player_id, stat.match_id) != (
                group[-1][0].player_id,
                group[-1][0].match_id,
            ):
                append_player_match(group)
                group.clear()
            group.append((stat, match, season_label))
            row_count += 1
        if group:
            append_player_match(group)
            group.clear()
    finally:
        await rows.close()
    if not row_count:
        raise ValueError()
    logger.info("canonical_history_loaded", rows=row_count)
    if not candidates:
        raise ValueError()
    latest_team_players: dict[uuid.UUID, list[tuple[uuid.UUID, str]]] = defaultdict(list)
    membership_date = (cutoff or max(item[0] for item in latest_membership.values())).date()
    for player_id, (last_seen, team_id, role) in latest_membership.items():
        if last_seen.date() >= membership_date - timedelta(days=365):
            latest_team_players[team_id].append((player_id, role))

    matches = list(
        (
            await session.scalars(
                select(Match).where(
                    Match.status == "finished",
                    Match.home_score.is_not(None),
                    Match.away_score.is_not(None),
                )
            )
        ).all()
    )
    team_stats = list(
        (await session.scalars(select(TeamMatchStat).order_by(TeamMatchStat.available_at))).all()
    )
    team_stat_map: dict[tuple[uuid.UUID, uuid.UUID], list[TeamMatchStat]] = defaultdict(list)
    for item in team_stats:
        team_stat_map[(item.match_id, item.team_id)].append(item)
        ingestion_ids.add(str(item.ingestion_run_id))
    team_records: list[dict[str, object]] = []
    for match in matches:
        for team_id, goals_for, goals_against in (
            (match.home_team_id, match.home_score, match.away_score),
            (match.away_team_id, match.away_score, match.home_score),
        ):
            team_records.extend(
                _team_history_versions(
                    match,
                    team_id,
                    goals_for,
                    goals_against,
                    team_stat_map.get((match.id, team_id), []),
                )
            )
    return CanonicalHistory(
        player_history=pl.DataFrame(
            player_records,
            schema_overrides={
                name: pl.Float64
                for name in (
                    "goals",
                    "assists",
                    "xg",
                    "xa",
                    "shots",
                    "tackles",
                    "interceptions",
                    "saves",
                )
            },
        ),
        team_history=pl.DataFrame(
            team_records,
            schema_overrides={
                name: pl.Float64
                for name in (
                    "goals_for",
                    "goals_against",
                    "xg_for",
                    "xg_against",
                    "cards",
                    "penalties",
                )
            },
        ),
        training_candidates=pl.DataFrame(candidates),
        labels=pl.DataFrame(
            labels,
            schema_overrides={name: pl.Float64 for name in labels[0] if name.startswith("label_")},
        ),
        latest_team_players=dict(latest_team_players),
        ingestion_run_ids=tuple(sorted(ingestion_ids)),
        latest_membership=latest_membership,
        membership_available_at=membership_available_at,
    )


def _team_history_versions(
    match: Match,
    team_id: uuid.UUID,
    goals_for: int | None,
    goals_against: int | None,
    details: list[TeamMatchStat],
) -> list[dict[str, object]]:

    earliest_result = historical_result_available_at(match.kickoff_at, match.kickoff_precision)
    updates: dict[datetime, dict[str, object]] = defaultdict(dict)
    updates[max(match.available_at, earliest_result)].update(
        goals_for=goals_for, goals_against=goals_against
    )
    for detail in details:
        updates[max(detail.available_at, earliest_result)].update(
            {
                key: value
                for key, value in detail.stats.items()
                if value is not None
                and not (
                    key in {"goals_for", "goals_against"}
                    and detail.field_provenance.get("canonical_result_agrees") is False
                )
            }
        )
    values: dict[str, object] = {}
    versions: list[dict[str, object]] = []
    for available_at, update_values in sorted(updates.items()):
        values.update(update_values)
        if values.get("goals_for") is None or values.get("goals_against") is None:
            continue
        yellow = _optional_number(values, "yellow_cards")
        red = _optional_number(values, "red_cards")
        versions.append(
            {
                "team_id": str(team_id),
                "event_time": match.kickoff_at,
                "available_at": available_at,
                "goals_for": values["goals_for"],
                "goals_against": values["goals_against"],
                "xg_for": _optional_number(values, "xg_for", "xg"),
                "xg_against": _optional_number(values, "xg_against"),
                "cards": yellow + red if yellow is not None and red is not None else None,
                "penalties": _optional_number(values, "penalties"),
                "referee_id": _known_referee(match, available_at),
            }
        )
    return versions


def _known_referee(match: Match, cutoff: datetime) -> str | None:
    if (
        match.referee_id is not None
        and match.referee_available_at is not None
        and match.referee_available_at <= cutoff
    ):
        return str(match.referee_id)
    return None


def _player_history_versions(
    details: list[PlayerMatchStat],
    match: Match,
    shot_xg: dict[tuple[uuid.UUID, uuid.UUID, uuid.UUID], ShotXg] | None = None,
) -> list[dict[str, object]]:

    known: dict[str, object] = {
        "player_id": str(details[0].player_id),
        "event_time": match.kickoff_at,
        **dict.fromkeys(
            ("goals", "assists", "xg", "xa", "shots", "tackles", "interceptions", "saves")
        ),
    }
    updates: dict[datetime, dict[str, object]] = defaultdict(dict)
    for stat in details:
        values = {
            "minutes": stat.minutes,
            "started": stat.started,
            "event_statistics_available": bool(stat.stats.get("event_statistics_available", 1)),
            "goals": _observed_number(stat.stats, "goals", "goals_scored"),
            "assists": _observed_number(stat.stats, "assists", "goal_assist"),
            "xg": _optional_number(stat.stats, "xg", "expected_goals"),
            "xa": _optional_number(stat.stats, "xa", "expected_assists"),
            "shots": _observed_number(stat.stats, "shots", "total_scoring_att"),
            "tackles": _observed_number(stat.stats, "tackles", "total_tackle"),
            "interceptions": _observed_number(stat.stats, "interceptions", "interception"),
            "saves": _observed_number(stat.stats, "saves", "total_saves"),
        }
        updates[stat.available_at].update(
            {key: value for key, value in values.items() if value is not None}
        )
        if values["xg"] is None and shot_xg is not None:
            shots = shot_xg.get((stat.source_id, stat.match_id, stat.player_id))
            xg = covered_xg(_observed_number(stat.stats, "shots", "total_scoring_att"), shots)
            if xg is not None:
                available_at = (
                    max(stat.available_at, shots.available_at) if shots else stat.available_at
                )
                updates[available_at]["xg"] = xg
    output = []
    for available_at, update in sorted(updates.items()):
        known.update(update)
        output.append({**known, "available_at": available_at})
    return output


async def _persist_snapshot(
    session: AsyncSession,
    settings: Settings,
    frame: pl.DataFrame,
    ingestion_ids: tuple[str, ...],
    *,
    kind: str,
) -> PreparedSnapshot:
    registered_names = {definition.name for definition in FeatureRegistry.load().definitions}
    feature_names = [name for name in frame.columns if name in registered_names]
    materialized = materialize_snapshot(
        frame,
        output_root=settings.data_root / "gold" / "features" / kind,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        source_manifest={"ingestion_run_ids": list(ingestion_ids), "kind": kind},
    )
    cutoff = frame["prediction_cutoff"].max()
    if not isinstance(cutoff, datetime):
        raise ValueError()
    existing = await session.scalar(
        select(FeatureSnapshotMetadata).where(
            FeatureSnapshotMetadata.feature_schema_version == FEATURE_SCHEMA_VERSION,
            FeatureSnapshotMetadata.prediction_cutoff == cutoff,
            FeatureSnapshotMetadata.manifest_hash == materialized.content_sha256,
        )
    )
    if existing is None:
        existing = FeatureSnapshotMetadata(
            feature_schema_version=FEATURE_SCHEMA_VERSION,
            prediction_cutoff=cutoff,
            training_cutoff=cutoff if kind == "training" else None,
            manifest_hash=materialized.content_sha256,
            storage_path=str(materialized.storage_path.resolve()),
            row_count=materialized.row_count,
            dataset_manifest={"ingestion_run_ids": list(ingestion_ids), "kind": kind},
            feature_names=feature_names,
        )
        session.add(existing)
        await session.commit()
    return PreparedSnapshot(existing, frame)


def _labels(
    row_id: str,
    stat: PlayerMatchStat,
    match: Match,
    season: str,
    role: str,
    is_home: bool,
) -> dict[str, object]:
    goals = _observed_number(stat.stats, "goals", "goals_scored")
    assists = _observed_number(stat.stats, "assists", "goal_assist")
    conceded = match.away_score if is_home else match.home_score
    scored = match.home_score if is_home else match.away_score
    labels: dict[str, object] = {
        "snapshot_row_id": row_id,
        "season": season,
        "football_role": role,
        "label_start_probability": float(stat.started),
        "label_appearance_probability": float(stat.minutes > 0),
        "label_expected_minutes": float(stat.minutes),
        "label_goal_probability": float(goals > 0) if goals is not None else None,
        "label_expected_goals": goals,
        "label_assist_probability": float(assists > 0) if assists is not None else None,
        "label_expected_assists": assists,
        "label_team_goals": scored,
        "label_team_goals_conceded": conceded,
        "label_clean_sheet_probability": float(conceded == 0),
        "label_goalkeeper_saves": _observed_number(stat.stats, "saves", "total_saves")
        if role == "GK"
        else None,
        "label_goalkeeper_goals_conceded": conceded if role == "GK" else None,
        "label_yellow_card_probability": _positive_event(stat.stats, "yellow_cards", "yellow_card"),
        "label_red_card_probability": _positive_event(stat.stats, "red_cards", "red_card"),
        "label_penalty_involvement": _any_event(
            [
                _observed_number(stat.stats, key)
                for key in (
                    "att_pen_goal",
                    "att_pen_target",
                    "att_pen_miss",
                    "att_pen_post",
                    "penalty_save",
                    "penalty_won",
                    "penalties_scored",
                    "penalties_missed",
                    "penalties_saved",
                    "penalties_won",
                )
            ]
        ),
        "label_base_rating": _optional_number(stat.stats, "base_rating", "rating"),
    }
    if not stat.stats.get("event_statistics_available", 1):
        for target in (
            "goal_probability",
            "expected_goals",
            "assist_probability",
            "expected_assists",
            "goalkeeper_saves",
            "yellow_card_probability",
            "red_card_probability",
            "penalty_involvement",
            "base_rating",
        ):
            labels[f"label_{target}"] = None
    return labels


def _observed_number(values: dict[str, object], *keys: str) -> float | None:
    if not values.get("event_statistics_available", 1):
        return None
    value = _optional_number(values, *keys)

    if value is None and any(key in values for key in keys):
        return None
    return value or 0.0


def _positive_event(values: dict[str, object], *keys: str) -> float | None:
    value = _observed_number(values, *keys)
    return float(value > 0) if value is not None else None


def _any_event(values: list[float | None]) -> float | None:
    if any(value is not None and value > 0 for value in values):
        return 1.0
    return None if any(value is None for value in values) else 0.0


def _optional_number(values: dict[str, object], *keys: str) -> float | None:
    for key in keys:
        value = values.get(key)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                continue
    return None


def _football_role(position: str | None) -> str:
    canonical = football_role(position)
    if canonical is not None:
        return canonical
    value = (position or "").casefold()
    if value in {"gk", "por", "goalkeeper", "portiere"}:
        return "GK"
    if value in {"def", "defender", "difensore", "dc", "dd", "ds"}:
        return "DEF"
    if value in {"fwd", "forward", "striker", "attaccante", "a", "pc"}:
        return "FWD"
    return "UNKNOWN"
