from __future__ import annotations

from collections.abc import Iterable, Mapping
from tempfile import TemporaryDirectory

import duckdb
import polars as pl

from markguardiola.features.point_in_time import assert_no_future_information


class PointInTimeSnapshotBuilder:
    def __init__(self, *, batch_size: int = 2048) -> None:
        if batch_size < 1:
            raise ValueError()
        self.batch_size = batch_size

    def build(
        self,
        *,
        candidates: pl.DataFrame,
        player_history: pl.DataFrame,
        team_history: pl.DataFrame,
        referee_history: pl.DataFrame | None = None,
    ) -> pl.DataFrame:
        candidates = _prepare_candidates(candidates)
        player_history = _prepare_player_history(player_history)
        team_history = _prepare_team_history(team_history)
        referee_history = _prepare_referee_history(referee_history, team_history)

        context_keys = [
            "team_id",
            "opponent_team_id",
            "match_id",
            "prediction_cutoff",
            "kickoff_at",
            "home_flag",
            "referee_id",
        ]
        contexts = candidates.unique(subset=context_keys, maintain_order=True).select(
            "snapshot_row_id", *context_keys
        )

        with (
            TemporaryDirectory(prefix="mark-features-") as temporary,
            duckdb.connect(
                ":memory:",
                config={"memory_limit": "512MB", "threads": "1", "temp_directory": temporary},
            ) as connection,
        ):
            connection.register("player_history", player_history.to_arrow())
            connection.register("team_history", team_history.to_arrow())
            connection.register("referee_history", referee_history.to_arrow())
            player = self._query_batches(connection, candidates, _PLAYER_SQL)
            team = self._query_batches(connection, contexts, _TEAM_SQL)
            opponent = self._query_batches(connection, contexts, _OPPONENT_SQL)
            referee = self._query_batches(connection, contexts, _REFEREE_SQL)

        contextual_features = (
            contexts.join(team, on="snapshot_row_id", how="left")
            .join(opponent, on="snapshot_row_id", how="left")
            .join(referee, on="snapshot_row_id", how="left")
            .drop("snapshot_row_id")
        )
        result = candidates.join(player, on="snapshot_row_id", how="left").join(
            contextual_features, on=context_keys, how="left", nulls_equal=True
        )
        zero_fill = [
            column
            for column in result.columns
            if (
                column.endswith(("_count", "_14d"))
                or column.startswith(
                    (
                        "minutes_last_",
                        "starts_last_",
                        "appearances_last_",
                        "team_goals_",
                        "opponent_goals_",
                    )
                )
            )
            and result[column].dtype.is_numeric()
        ]
        if zero_fill:
            result = result.with_columns(
                pl.col(
                    [
                        column
                        for column in zero_fill
                        if not column.startswith(("goals_", "assists_"))
                    ]
                ).fill_null(0)
            )
        assert_no_future_information(result)
        return result.sort("snapshot_row_id")

    def _query_batches(
        self, connection: duckdb.DuckDBPyConnection, candidates: pl.DataFrame, query: str
    ) -> pl.DataFrame:
        frames = []

        for offset in range(0, max(1, candidates.height), self.batch_size):
            connection.register("candidates", candidates.slice(offset, self.batch_size).to_arrow())
            try:
                frames.append(connection.sql(query).pl())
            finally:
                connection.unregister("candidates")
        return pl.concat(frames)


def _prepare_candidates(frame: pl.DataFrame) -> pl.DataFrame:
    required = {
        "snapshot_row_id",
        "player_id",
        "team_id",
        "opponent_team_id",
        "match_id",
        "prediction_cutoff",
        "kickoff_at",
        "home_flag",
    }
    _require(frame, required, "candidates")
    if "referee_id" not in frame.columns:
        frame = frame.with_columns(pl.lit(None, dtype=pl.String).alias("referee_id"))
    return frame


def _prepare_player_history(frame: pl.DataFrame) -> pl.DataFrame:
    required = {"player_id", "event_time", "available_at", "minutes", "started"}
    _require(frame, required, "player_history")
    defaults: dict[str, int | float | None] = {
        "event_statistics_available": 1,
        "goals": None,
        "assists": None,
        "xg": None,
        "xa": None,
        "shots": None,
        "tackles": None,
        "interceptions": None,
        "saves": None,
    }
    return _add_defaults(frame, defaults)


def _prepare_team_history(frame: pl.DataFrame) -> pl.DataFrame:
    required = {"team_id", "event_time", "available_at", "goals_for", "goals_against"}
    _require(frame, required, "team_history")
    defaults: dict[str, int | float | str | None] = {
        "xg_for": None,
        "xg_against": None,
        "cards": None,
        "penalties": None,
        "referee_id": None,
    }
    return _add_defaults(frame, defaults)


def _prepare_referee_history(
    frame: pl.DataFrame | None, team_history: pl.DataFrame
) -> pl.DataFrame:
    if frame is None:
        history = team_history.filter(pl.col("referee_id").is_not_null())
        keys = ["referee_id", "event_time"]
        boundaries = history.select(*keys, "available_at").unique()
        clubs = history.select(*keys, "team_id").unique()
        grid = boundaries.join(clubs, on=keys).sort("available_at")
        latest = grid.join_asof(
            history.select(*keys, "team_id", "available_at", "cards", "penalties").sort(
                "available_at"
            ),
            on="available_at",
            by=[*keys, "team_id"],
            strategy="backward",
            check_sortedness=False,
        )
        return latest.group_by(*keys, "available_at").agg(
            *[
                pl.when((pl.len() == 2) & (pl.col(metric).count() == 2))
                .then(pl.col(metric).sum())
                .otherwise(None)
                .cast(pl.Float64)
                .alias(metric)
                for metric in ("cards", "penalties")
            ]
        )
    _require(
        frame,
        {"referee_id", "event_time", "available_at", "cards", "penalties"},
        "referee_history",
    )
    return frame


def _add_defaults(frame: pl.DataFrame, defaults: Mapping[str, object]) -> pl.DataFrame:
    expressions = [
        pl.lit(value).alias(column)
        for column, value in defaults.items()
        if column not in frame.columns
    ]
    return frame.with_columns(expressions) if expressions else frame


def _require(frame: pl.DataFrame, required: Iterable[str], label: str) -> None:
    missing = set(required).difference(frame.columns)
    if missing:
        raise ValueError()


_PLAYER_SQL = """
WITH versions AS (
    SELECT
        c.snapshot_row_id,
        h.event_time,
        h.available_at,
        h.minutes,
        CAST(h.started AS INTEGER) AS started,
        h.goals,
        h.assists,
        h.xg,
        h.xa,
        h.shots,
        h.tackles,
        h.interceptions,
        h.saves,
        h.event_statistics_available,
        ROW_NUMBER() OVER (
            PARTITION BY c.snapshot_row_id, h.event_time ORDER BY h.available_at DESC
        ) AS version_rank
    FROM candidates c
    JOIN player_history h
      ON h.player_id = c.player_id
     AND h.event_time < c.prediction_cutoff
     AND h.available_at <= c.prediction_cutoff
), eligible AS (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY snapshot_row_id ORDER BY event_time DESC
    ) AS recency
    FROM versions WHERE version_rank = 1
), aggregated AS (
    SELECT
        snapshot_row_id,
        COUNT(*) FILTER (WHERE recency <= 10) AS player_history_count,
        COUNT(*) FILTER (WHERE recency <= 10 AND event_statistics_available)
          AS event_history_count,
        SUM(minutes) FILTER (WHERE recency <= 1) AS minutes_last_1,
        SUM(minutes) FILTER (WHERE recency <= 3) AS minutes_last_3,
        SUM(minutes) FILTER (WHERE recency <= 5) AS minutes_last_5,
        SUM(minutes) FILTER (WHERE recency <= 10) AS minutes_last_10,
        SUM(started) FILTER (WHERE recency <= 5) AS starts_last_5,
        SUM(goals) FILTER (WHERE recency <= 5) AS goals_last_5,
        SUM(assists) FILTER (WHERE recency <= 5) AS assists_last_5,
        SUM(minutes * EXP(-0.35 * (recency - 1))) FILTER (WHERE recency <= 10)
          / NULLIF(SUM(EXP(-0.35 * (recency - 1))) FILTER (WHERE recency <= 10), 0)
          AS minutes_ewma_10,
        90 * SUM(xg) FILTER (WHERE recency <= 10)
          / NULLIF(SUM(minutes) FILTER (WHERE recency <= 10 AND xg IS NOT NULL), 0)
          AS xg_per90_last_10,
        90 * SUM(xa) FILTER (WHERE recency <= 10)
          / NULLIF(SUM(minutes) FILTER (WHERE recency <= 10 AND xa IS NOT NULL), 0)
          AS xa_per90_last_10,
        90 * SUM(shots) FILTER (WHERE recency <= 5)
          / NULLIF(SUM(minutes) FILTER (WHERE recency <= 5 AND shots IS NOT NULL), 0)
          AS shots_per90_last_5,
        90 * SUM(tackles) FILTER (WHERE recency <= 10)
          / NULLIF(SUM(minutes) FILTER (WHERE recency <= 10 AND tackles IS NOT NULL), 0)
          AS tackles_per90_last_10,
        90 * SUM(interceptions) FILTER (WHERE recency <= 10)
          / NULLIF(SUM(minutes) FILTER (WHERE recency <= 10 AND interceptions IS NOT NULL), 0)
          AS interceptions_per90_last_10,
        90 * SUM(saves) FILTER (WHERE recency <= 10)
          / NULLIF(SUM(minutes) FILTER (WHERE recency <= 10 AND saves IS NOT NULL), 0)
          AS saves_per90_last_10,
        STDDEV_SAMP(minutes) FILTER (WHERE recency <= 10) AS minutes_volatility_10,
        -REGR_SLOPE(minutes, recency) FILTER (WHERE recency <= 5) AS minutes_trend_5,
        MAX(available_at) AS player_max_available_at
    FROM eligible
    GROUP BY snapshot_row_id
)
SELECT * FROM aggregated
"""

_TEAM_SQL = """
WITH versions AS (
    SELECT
        c.snapshot_row_id,
        c.kickoff_at,
        c.prediction_cutoff,
        h.event_time,
        h.available_at,
        h.goals_for,
        h.goals_against,
        h.xg_for,
        h.xg_against,
        ROW_NUMBER() OVER (
            PARTITION BY c.snapshot_row_id, h.event_time ORDER BY h.available_at DESC
        ) AS version_rank
    FROM candidates c
    JOIN team_history h
      ON h.team_id = c.team_id
     AND h.event_time < c.prediction_cutoff
     AND h.available_at <= c.prediction_cutoff
), eligible AS (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY snapshot_row_id ORDER BY event_time DESC
    ) AS recency
    FROM versions WHERE version_rank = 1
)
SELECT
    snapshot_row_id,
    COUNT(*) FILTER (WHERE recency <= 10) AS team_history_count,
    SUM(goals_for) FILTER (WHERE recency <= 5) AS team_goals_for_last_5,
    SUM(goals_against) FILTER (WHERE recency <= 5) AS team_goals_against_last_5,
    SUM(xg_for * EXP(-0.35 * (recency - 1))) FILTER (WHERE recency <= 10)
      / NULLIF(SUM(EXP(-0.35 * (recency - 1)))
          FILTER (WHERE recency <= 10 AND xg_for IS NOT NULL), 0)
      AS team_xg_for_ewma_10,
    SUM(xg_against * EXP(-0.35 * (recency - 1))) FILTER (WHERE recency <= 10)
      / NULLIF(SUM(EXP(-0.35 * (recency - 1)))
          FILTER (WHERE recency <= 10 AND xg_against IS NOT NULL), 0)
      AS team_xg_against_ewma_10,
    DATE_DIFF('day', MAX(event_time), MAX(kickoff_at)) AS rest_days,
    COUNT(*) FILTER (
      WHERE event_time >= prediction_cutoff - INTERVAL 14 DAY
    ) AS schedule_congestion_14d,
    MAX(available_at) AS team_max_available_at
FROM eligible
GROUP BY snapshot_row_id
"""

_OPPONENT_SQL = """
WITH versions AS (
    SELECT
        c.snapshot_row_id,
        h.event_time,
        h.available_at,
        h.goals_for,
        h.goals_against,
        h.xg_against,
        ROW_NUMBER() OVER (
            PARTITION BY c.snapshot_row_id, h.event_time ORDER BY h.available_at DESC
        ) AS version_rank
    FROM candidates c
    JOIN team_history h
      ON h.team_id = c.opponent_team_id
     AND h.event_time < c.prediction_cutoff
     AND h.available_at <= c.prediction_cutoff
), eligible AS (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY snapshot_row_id ORDER BY event_time DESC
    ) AS recency
    FROM versions WHERE version_rank = 1
)
SELECT
    snapshot_row_id,
    COUNT(*) FILTER (WHERE recency <= 10) AS opponent_history_count,
    SUM(goals_for) FILTER (WHERE recency <= 5) AS opponent_goals_for_last_5,
    SUM(goals_against) FILTER (WHERE recency <= 5) AS opponent_goals_against_last_5,
    SUM(xg_against * EXP(-0.35 * (recency - 1))) FILTER (WHERE recency <= 10)
      / NULLIF(SUM(EXP(-0.35 * (recency - 1)))
          FILTER (WHERE recency <= 10 AND xg_against IS NOT NULL), 0)
      AS opponent_xg_against_ewma_10,
    MAX(available_at) AS opponent_max_available_at
FROM eligible
GROUP BY snapshot_row_id
"""

_REFEREE_SQL = """
WITH versions AS (
    SELECT
        c.snapshot_row_id,
        h.event_time,
        h.available_at,
        h.cards,
        h.penalties,
        ROW_NUMBER() OVER (
            PARTITION BY c.snapshot_row_id, h.event_time ORDER BY h.available_at DESC
        ) AS version_rank
    FROM candidates c
    JOIN referee_history h
      ON h.referee_id = c.referee_id
     AND c.referee_id IS NOT NULL
     AND h.event_time < c.prediction_cutoff
     AND h.available_at <= c.prediction_cutoff
), eligible AS (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY snapshot_row_id ORDER BY event_time DESC
    ) AS recency FROM versions WHERE version_rank = 1
)
SELECT
    snapshot_row_id,
    COUNT(*) FILTER (WHERE recency <= 20) AS referee_history_count,
    (SUM(cards) FILTER (WHERE recency <= 20) + 5 * 4.5)
      / (COUNT(cards) FILTER (WHERE recency <= 20) + 5) AS referee_cards_per_match_20,
    (SUM(penalties) FILTER (WHERE recency <= 20) + 10 * 0.25)
      / (COUNT(penalties) FILTER (WHERE recency <= 20) + 10) AS referee_penalties_per_match_20,
    MAX(available_at) AS referee_max_available_at
FROM eligible
GROUP BY snapshot_row_id
"""
