from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "519500e5295e"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:

    op.create_table(
        "background_jobs",
        sa.Column("queue_job_id", sa.String(length=128), nullable=True),
        sa.Column("job_type", sa.String(length=96), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("parameters", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("progress", sa.Float(), nullable=False),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_background_jobs")),
        sa.UniqueConstraint("queue_job_id", name=op.f("uq_background_jobs_queue_job_id")),
    )
    op.create_table(
        "coaches",
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("normalized_name", sa.String(length=200), nullable=False),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("nationality_code", sa.String(length=3), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_coaches")),
    )
    op.create_index(
        op.f("ix_coaches_normalized_name"), "coaches", ["normalized_name"], unique=False
    )
    op.create_table(
        "competitions",
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("country_code", sa.String(length=3), nullable=False),
        sa.Column("competition_type", sa.String(length=32), nullable=False),
        sa.Column("gender", sa.String(length=16), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_competitions")),
        sa.UniqueConstraint("country_code", "name", name=op.f("uq_competitions_country_code")),
    )
    op.create_table(
        "data_sources",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=True),
        sa.Column("adapter_version", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("capabilities", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_data_sources")),
        sa.UniqueConstraint("key", name=op.f("uq_data_sources_key")),
    )
    op.create_table(
        "feature_snapshot_metadata",
        sa.Column("feature_schema_version", sa.String(length=64), nullable=False),
        sa.Column("prediction_cutoff", sa.DateTime(timezone=True), nullable=False),
        sa.Column("training_cutoff", sa.DateTime(timezone=True), nullable=True),
        sa.Column("manifest_hash", sa.String(length=64), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("row_count", sa.BigInteger(), nullable=False),
        sa.Column("dataset_manifest", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("feature_names", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_feature_snapshot_metadata")),
        sa.UniqueConstraint(
            "feature_schema_version",
            "prediction_cutoff",
            "manifest_hash",
            name=op.f("uq_feature_snapshot_metadata_feature_schema_version"),
        ),
    )
    op.create_table(
        "model_versions",
        sa.Column("target", sa.String(length=96), nullable=False),
        sa.Column("version", sa.String(length=96), nullable=False),
        sa.Column("algorithm", sa.String(length=96), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("trained_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("training_cutoff", sa.DateTime(timezone=True), nullable=False),
        sa.Column("feature_schema_version", sa.String(length=64), nullable=False),
        sa.Column("code_revision", sa.String(length=64), nullable=True),
        sa.Column("artifact_path", sa.Text(), nullable=False),
        sa.Column("parameters", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("subgroup_metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("calibration", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_model_versions")),
        sa.UniqueConstraint("target", "version", name=op.f("uq_model_versions_target")),
    )
    op.create_table(
        "players",
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("normalized_name", sa.String(length=200), nullable=False),
        sa.Column("given_name", sa.String(length=100), nullable=True),
        sa.Column("family_name", sa.String(length=100), nullable=True),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("nationality_code", sa.String(length=3), nullable=True),
        sa.Column("primary_position", sa.String(length=32), nullable=True),
        sa.Column("preferred_foot", sa.String(length=16), nullable=True),
        sa.Column("height_cm", sa.SmallInteger(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_players")),
    )
    op.create_index(
        "ix_players_identity", "players", ["normalized_name", "date_of_birth"], unique=False
    )
    op.create_table(
        "recommendation_explanations",
        sa.Column("recommendation_type", sa.String(length=32), nullable=False),
        sa.Column("recommendation_id", sa.UUID(), nullable=False),
        sa.Column("rank", sa.SmallInteger(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("evidence_type", sa.String(length=64), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recommendation_explanations")),
    )
    op.create_index(
        "ix_explanation_owner",
        "recommendation_explanations",
        ["recommendation_type", "recommendation_id"],
        unique=False,
    )
    op.create_table(
        "referees",
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("normalized_name", sa.String(length=200), nullable=False),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("nationality_code", sa.String(length=3), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_referees")),
    )
    op.create_index(
        op.f("ix_referees_normalized_name"), "referees", ["normalized_name"], unique=False
    )
    op.create_table(
        "teams",
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("normalized_name", sa.String(length=160), nullable=False),
        sa.Column("short_name", sa.String(length=64), nullable=True),
        sa.Column("country_code", sa.String(length=3), nullable=True),
        sa.Column("founded_year", sa.SmallInteger(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_teams")),
    )
    op.create_index(op.f("ix_teams_normalized_name"), "teams", ["normalized_name"], unique=False)
    op.create_table(
        "users",
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("local_identity", sa.String(length=160), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("local_identity", name=op.f("uq_users_local_identity")),
    )
    op.create_table(
        "venues",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("country_code", sa.String(length=3), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("capacity", sa.Integer(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_venues")),
    )
    op.create_table(
        "ingestion_runs",
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("requested_scope", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_revision", sa.String(length=160), nullable=True),
        sa.Column("code_revision", sa.String(length=64), nullable=True),
        sa.Column("records_seen", sa.BigInteger(), nullable=False),
        sa.Column("records_written", sa.BigInteger(), nullable=False),
        sa.Column("records_rejected", sa.BigInteger(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("manifest", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["data_sources.id"],
            name=op.f("fk_ingestion_runs_source_id_data_sources"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ingestion_runs")),
    )
    op.create_table(
        "player_team_periods",
        sa.Column("player_id", sa.UUID(), nullable=False),
        sa.Column("team_id", sa.UUID(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("squad_number", sa.SmallInteger(), nullable=True),
        sa.Column("position", sa.String(length=32), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from",
            name=op.f("ck_player_team_periods_valid_dates"),
        ),
        sa.ForeignKeyConstraint(
            ["player_id"], ["players.id"], name=op.f("fk_player_team_periods_player_id_players")
        ),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], name=op.f("fk_player_team_periods_team_id_teams")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_player_team_periods")),
        sa.UniqueConstraint(
            "player_id", "team_id", "valid_from", name=op.f("uq_player_team_periods_player_id")
        ),
    )
    op.create_table(
        "prediction_runs",
        sa.Column("prediction_cutoff", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_cutoff", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model_versions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("feature_snapshot_id", sa.UUID(), nullable=False),
        sa.Column("code_revision", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["feature_snapshot_id"],
            ["feature_snapshot_metadata.id"],
            name=op.f("fk_prediction_runs_feature_snapshot_id_feature_snapshot_metadata"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_prediction_runs")),
    )
    op.create_table(
        "provider_entity_map",
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("provider_entity_id", sa.String(length=256), nullable=False),
        sa.Column("canonical_entity_id", sa.UUID(), nullable=False),
        sa.Column("normalized_name", sa.String(length=256), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("mapping_method", sa.String(length=32), nullable=False),
        sa.Column("manually_confirmed", sa.Boolean(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name=op.f("ck_provider_entity_map_confidence_range"),
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["data_sources.id"],
            name=op.f("fk_provider_entity_map_source_id_data_sources"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_provider_entity_map")),
        sa.UniqueConstraint(
            "source_id",
            "entity_type",
            "provider_entity_id",
            name=op.f("uq_provider_entity_map_source_id"),
        ),
    )
    op.create_index(
        "ix_provider_entity_canonical",
        "provider_entity_map",
        ["entity_type", "canonical_entity_id"],
        unique=False,
    )
    op.create_table(
        "schema_versions",
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("entity_name", sa.String(length=128), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("fields", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["data_sources.id"],
            name=op.f("fk_schema_versions_source_id_data_sources"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_schema_versions")),
        sa.UniqueConstraint(
            "source_id", "entity_name", "version", name=op.f("uq_schema_versions_source_id")
        ),
    )
    op.create_table(
        "seasons",
        sa.Column("competition_id", sa.UUID(), nullable=False),
        sa.Column("label", sa.String(length=32), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("current", sa.Boolean(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["competition_id"],
            ["competitions.id"],
            name=op.f("fk_seasons_competition_id_competitions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_seasons")),
        sa.UniqueConstraint("competition_id", "label", name=op.f("uq_seasons_competition_id")),
    )
    op.create_table(
        "data_quality_issues",
        sa.Column("ingestion_run_id", sa.UUID(), nullable=True),
        sa.Column("source_id", sa.UUID(), nullable=True),
        sa.Column("rule_key", sa.String(length=128), nullable=False),
        sa.Column("severity", sa.String(length=24), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=True),
        sa.Column("entity_id", sa.UUID(), nullable=True),
        sa.Column("provider_record_id", sa.String(length=256), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["ingestion_runs.id"],
            name=op.f("fk_data_quality_issues_ingestion_run_id_ingestion_runs"),
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["data_sources.id"],
            name=op.f("fk_data_quality_issues_source_id_data_sources"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_data_quality_issues")),
    )
    op.create_index(
        "ix_quality_run_severity",
        "data_quality_issues",
        ["ingestion_run_id", "severity"],
        unique=False,
    )
    op.create_table(
        "injuries",
        sa.Column("player_id", sa.UUID(), nullable=False),
        sa.Column("team_id", sa.UUID(), nullable=True),
        sa.Column("injury_type", sa.String(length=160), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("started_on", sa.Date(), nullable=True),
        sa.Column("expected_return_on", sa.Date(), nullable=True),
        sa.Column("ended_on", sa.Date(), nullable=True),
        sa.Column("certainty", sa.Float(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("ingestion_run_id", sa.UUID(), nullable=False),
        sa.Column("schema_version_id", sa.UUID(), nullable=True),
        sa.Column("source_record_id", sa.String(length=512), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("field_provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["ingestion_runs.id"],
            name=op.f("fk_injuries_ingestion_run_id_ingestion_runs"),
        ),
        sa.ForeignKeyConstraint(
            ["player_id"], ["players.id"], name=op.f("fk_injuries_player_id_players")
        ),
        sa.ForeignKeyConstraint(
            ["schema_version_id"],
            ["schema_versions.id"],
            name=op.f("fk_injuries_schema_version_id_schema_versions"),
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["data_sources.id"], name=op.f("fk_injuries_source_id_data_sources")
        ),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], name=op.f("fk_injuries_team_id_teams")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_injuries")),
        sa.UniqueConstraint("source_id", "source_record_id", name=op.f("uq_injuries_source_id")),
    )
    op.create_table(
        "leagues",
        sa.Column("owner_user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("competition_id", sa.UUID(), nullable=True),
        sa.Column("season_id", sa.UUID(), nullable=True),
        sa.Column("head_to_head_enabled", sa.Boolean(), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["competition_id"],
            ["competitions.id"],
            name=op.f("fk_leagues_competition_id_competitions"),
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], ["users.id"], name=op.f("fk_leagues_owner_user_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["season_id"], ["seasons.id"], name=op.f("fk_leagues_season_id_seasons")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_leagues")),
    )
    op.create_table(
        "matches",
        sa.Column("season_id", sa.UUID(), nullable=False),
        sa.Column("home_team_id", sa.UUID(), nullable=False),
        sa.Column("away_team_id", sa.UUID(), nullable=False),
        sa.Column("venue_id", sa.UUID(), nullable=True),
        sa.Column("referee_id", sa.UUID(), nullable=True),
        sa.Column("home_coach_id", sa.UUID(), nullable=True),
        sa.Column("away_coach_id", sa.UUID(), nullable=True),
        sa.Column("kickoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("matchweek", sa.SmallInteger(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("home_score", sa.SmallInteger(), nullable=True),
        sa.Column("away_score", sa.SmallInteger(), nullable=True),
        sa.Column("home_score_extra", sa.SmallInteger(), nullable=True),
        sa.Column("away_score_extra", sa.SmallInteger(), nullable=True),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("home_team_id <> away_team_id", name=op.f("ck_matches_different_teams")),
        sa.ForeignKeyConstraint(
            ["away_coach_id"], ["coaches.id"], name=op.f("fk_matches_away_coach_id_coaches")
        ),
        sa.ForeignKeyConstraint(
            ["away_team_id"], ["teams.id"], name=op.f("fk_matches_away_team_id_teams")
        ),
        sa.ForeignKeyConstraint(
            ["home_coach_id"], ["coaches.id"], name=op.f("fk_matches_home_coach_id_coaches")
        ),
        sa.ForeignKeyConstraint(
            ["home_team_id"], ["teams.id"], name=op.f("fk_matches_home_team_id_teams")
        ),
        sa.ForeignKeyConstraint(
            ["referee_id"], ["referees.id"], name=op.f("fk_matches_referee_id_referees")
        ),
        sa.ForeignKeyConstraint(
            ["season_id"], ["seasons.id"], name=op.f("fk_matches_season_id_seasons")
        ),
        sa.ForeignKeyConstraint(
            ["venue_id"], ["venues.id"], name=op.f("fk_matches_venue_id_venues")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_matches")),
        sa.UniqueConstraint(
            "season_id",
            "home_team_id",
            "away_team_id",
            "kickoff_at",
            name=op.f("uq_matches_season_id"),
        ),
    )
    op.create_index("ix_matches_kickoff", "matches", ["kickoff_at"], unique=False)
    op.create_table(
        "raw_objects",
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("ingestion_run_id", sa.UUID(), nullable=False),
        sa.Column("schema_version_id", sa.UUID(), nullable=True),
        sa.Column("provider_object_id", sa.String(length=512), nullable=True),
        sa.Column("request_url", sa.Text(), nullable=True),
        sa.Column("request_params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("media_type", sa.String(length=128), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("content_bytes", sa.BigInteger(), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("http_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["ingestion_runs.id"],
            name=op.f("fk_raw_objects_ingestion_run_id_ingestion_runs"),
        ),
        sa.ForeignKeyConstraint(
            ["schema_version_id"],
            ["schema_versions.id"],
            name=op.f("fk_raw_objects_schema_version_id_schema_versions"),
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["data_sources.id"], name=op.f("fk_raw_objects_source_id_data_sources")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_raw_objects")),
        sa.UniqueConstraint("source_id", "content_sha256", name=op.f("uq_raw_objects_source_id")),
    )
    op.create_index(
        "ix_raw_objects_ingestion_run", "raw_objects", ["ingestion_run_id"], unique=False
    )
    op.create_table(
        "suspensions",
        sa.Column("player_id", sa.UUID(), nullable=False),
        sa.Column("team_id", sa.UUID(), nullable=True),
        sa.Column("reason", sa.String(length=160), nullable=True),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=True),
        sa.Column("match_count", sa.SmallInteger(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("ingestion_run_id", sa.UUID(), nullable=False),
        sa.Column("schema_version_id", sa.UUID(), nullable=True),
        sa.Column("source_record_id", sa.String(length=512), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("field_provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["ingestion_runs.id"],
            name=op.f("fk_suspensions_ingestion_run_id_ingestion_runs"),
        ),
        sa.ForeignKeyConstraint(
            ["player_id"], ["players.id"], name=op.f("fk_suspensions_player_id_players")
        ),
        sa.ForeignKeyConstraint(
            ["schema_version_id"],
            ["schema_versions.id"],
            name=op.f("fk_suspensions_schema_version_id_schema_versions"),
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["data_sources.id"], name=op.f("fk_suspensions_source_id_data_sources")
        ),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], name=op.f("fk_suspensions_team_id_teams")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_suspensions")),
        sa.UniqueConstraint("source_id", "source_record_id", name=op.f("uq_suspensions_source_id")),
    )
    op.create_table(
        "transfers",
        sa.Column("player_id", sa.UUID(), nullable=False),
        sa.Column("from_team_id", sa.UUID(), nullable=True),
        sa.Column("to_team_id", sa.UUID(), nullable=True),
        sa.Column("transfer_date", sa.Date(), nullable=False),
        sa.Column("transfer_type", sa.String(length=64), nullable=True),
        sa.Column("fee_eur", sa.Numeric(precision=16, scale=2), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("ingestion_run_id", sa.UUID(), nullable=False),
        sa.Column("schema_version_id", sa.UUID(), nullable=True),
        sa.Column("source_record_id", sa.String(length=512), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("field_provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["from_team_id"], ["teams.id"], name=op.f("fk_transfers_from_team_id_teams")
        ),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["ingestion_runs.id"],
            name=op.f("fk_transfers_ingestion_run_id_ingestion_runs"),
        ),
        sa.ForeignKeyConstraint(
            ["player_id"], ["players.id"], name=op.f("fk_transfers_player_id_players")
        ),
        sa.ForeignKeyConstraint(
            ["schema_version_id"],
            ["schema_versions.id"],
            name=op.f("fk_transfers_schema_version_id_schema_versions"),
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["data_sources.id"], name=op.f("fk_transfers_source_id_data_sources")
        ),
        sa.ForeignKeyConstraint(
            ["to_team_id"], ["teams.id"], name=op.f("fk_transfers_to_team_id_teams")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_transfers")),
        sa.UniqueConstraint("source_id", "source_record_id", name=op.f("uq_transfers_source_id")),
    )
    op.create_table(
        "events",
        sa.Column("match_id", sa.UUID(), nullable=False),
        sa.Column("team_id", sa.UUID(), nullable=True),
        sa.Column("player_id", sa.UUID(), nullable=True),
        sa.Column("related_player_id", sa.UUID(), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("event_subtype", sa.String(length=96), nullable=True),
        sa.Column("period", sa.SmallInteger(), nullable=True),
        sa.Column("second", sa.Integer(), nullable=True),
        sa.Column("x", sa.Float(), nullable=True),
        sa.Column("y", sa.Float(), nullable=True),
        sa.Column("detail", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("ingestion_run_id", sa.UUID(), nullable=False),
        sa.Column("schema_version_id", sa.UUID(), nullable=True),
        sa.Column("source_record_id", sa.String(length=512), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("field_provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["ingestion_runs.id"],
            name=op.f("fk_events_ingestion_run_id_ingestion_runs"),
        ),
        sa.ForeignKeyConstraint(
            ["match_id"], ["matches.id"], name=op.f("fk_events_match_id_matches")
        ),
        sa.ForeignKeyConstraint(
            ["player_id"], ["players.id"], name=op.f("fk_events_player_id_players")
        ),
        sa.ForeignKeyConstraint(
            ["related_player_id"], ["players.id"], name=op.f("fk_events_related_player_id_players")
        ),
        sa.ForeignKeyConstraint(
            ["schema_version_id"],
            ["schema_versions.id"],
            name=op.f("fk_events_schema_version_id_schema_versions"),
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["data_sources.id"], name=op.f("fk_events_source_id_data_sources")
        ),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], name=op.f("fk_events_team_id_teams")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_events")),
        sa.UniqueConstraint("source_id", "source_record_id", name=op.f("uq_events_source_id")),
    )
    op.create_index(
        "ix_events_match_period_second", "events", ["match_id", "period", "second"], unique=False
    )
    op.create_table(
        "league_members",
        sa.Column("league_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("is_owner", sa.Boolean(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["league_id"], ["leagues.id"], name=op.f("fk_league_members_league_id_leagues")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_league_members_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_league_members")),
        sa.UniqueConstraint("league_id", "user_id", name=op.f("uq_league_members_league_id")),
    )
    op.create_table(
        "league_rules",
        sa.Column("league_id", sa.UUID(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scoring", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("formations", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("roster_constraints", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("substitution_rules", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["league_id"], ["leagues.id"], name=op.f("fk_league_rules_league_id_leagues")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_league_rules")),
        sa.UniqueConstraint("league_id", "version", name=op.f("uq_league_rules_league_id")),
    )
    op.create_table(
        "lineups",
        sa.Column("match_id", sa.UUID(), nullable=False),
        sa.Column("team_id", sa.UUID(), nullable=False),
        sa.Column("player_id", sa.UUID(), nullable=False),
        sa.Column("is_starting", sa.Boolean(), nullable=False),
        sa.Column("shirt_number", sa.SmallInteger(), nullable=True),
        sa.Column("position", sa.String(length=32), nullable=True),
        sa.Column("formation_slot", sa.String(length=32), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("ingestion_run_id", sa.UUID(), nullable=False),
        sa.Column("schema_version_id", sa.UUID(), nullable=True),
        sa.Column("source_record_id", sa.String(length=512), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("field_provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["ingestion_runs.id"],
            name=op.f("fk_lineups_ingestion_run_id_ingestion_runs"),
        ),
        sa.ForeignKeyConstraint(
            ["match_id"], ["matches.id"], name=op.f("fk_lineups_match_id_matches")
        ),
        sa.ForeignKeyConstraint(
            ["player_id"], ["players.id"], name=op.f("fk_lineups_player_id_players")
        ),
        sa.ForeignKeyConstraint(
            ["schema_version_id"],
            ["schema_versions.id"],
            name=op.f("fk_lineups_schema_version_id_schema_versions"),
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["data_sources.id"], name=op.f("fk_lineups_source_id_data_sources")
        ),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], name=op.f("fk_lineups_team_id_teams")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lineups")),
        sa.UniqueConstraint("source_id", "source_record_id", name=op.f("uq_lineups_source_id")),
    )
    op.create_table(
        "market_entries",
        sa.Column("league_id", sa.UUID(), nullable=False),
        sa.Column("player_id", sa.UUID(), nullable=False),
        sa.Column("available", sa.Boolean(), nullable=False),
        sa.Column("asking_price", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("imported_name", sa.String(length=256), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["league_id"], ["leagues.id"], name=op.f("fk_market_entries_league_id_leagues")
        ),
        sa.ForeignKeyConstraint(
            ["player_id"], ["players.id"], name=op.f("fk_market_entries_player_id_players")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_market_entries")),
        sa.UniqueConstraint("league_id", "player_id", name=op.f("uq_market_entries_league_id")),
    )
    op.create_table(
        "odds_snapshots",
        sa.Column("match_id", sa.UUID(), nullable=False),
        sa.Column("bookmaker", sa.String(length=128), nullable=False),
        sa.Column("market", sa.String(length=128), nullable=False),
        sa.Column("selection", sa.String(length=128), nullable=False),
        sa.Column("decimal_odds", sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("ingestion_run_id", sa.UUID(), nullable=False),
        sa.Column("schema_version_id", sa.UUID(), nullable=True),
        sa.Column("source_record_id", sa.String(length=512), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("field_provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["ingestion_runs.id"],
            name=op.f("fk_odds_snapshots_ingestion_run_id_ingestion_runs"),
        ),
        sa.ForeignKeyConstraint(
            ["match_id"], ["matches.id"], name=op.f("fk_odds_snapshots_match_id_matches")
        ),
        sa.ForeignKeyConstraint(
            ["schema_version_id"],
            ["schema_versions.id"],
            name=op.f("fk_odds_snapshots_schema_version_id_schema_versions"),
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["data_sources.id"],
            name=op.f("fk_odds_snapshots_source_id_data_sources"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_odds_snapshots")),
        sa.UniqueConstraint(
            "source_id", "source_record_id", name=op.f("uq_odds_snapshots_source_id")
        ),
    )
    op.create_index(
        "ix_odds_match_available", "odds_snapshots", ["match_id", "available_at"], unique=False
    )
    op.create_table(
        "player_fantasy_roles",
        sa.Column("league_id", sa.UUID(), nullable=False),
        sa.Column("player_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["league_id"], ["leagues.id"], name=op.f("fk_player_fantasy_roles_league_id_leagues")
        ),
        sa.ForeignKeyConstraint(
            ["player_id"], ["players.id"], name=op.f("fk_player_fantasy_roles_player_id_players")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_player_fantasy_roles")),
        sa.UniqueConstraint(
            "league_id", "player_id", "role", name=op.f("uq_player_fantasy_roles_league_id")
        ),
    )
    op.create_table(
        "player_match_predictions",
        sa.Column("prediction_run_id", sa.UUID(), nullable=False),
        sa.Column("match_id", sa.UUID(), nullable=False),
        sa.Column("player_id", sa.UUID(), nullable=False),
        sa.Column("target", sa.String(length=96), nullable=False),
        sa.Column("expected_value", sa.Float(), nullable=False),
        sa.Column("median", sa.Float(), nullable=False),
        sa.Column("p10", sa.Float(), nullable=False),
        sa.Column("p90", sa.Float(), nullable=False),
        sa.Column("probability", sa.Float(), nullable=True),
        sa.Column("reliability", sa.Float(), nullable=False),
        sa.Column("distribution", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("model_version_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "reliability >= 0 AND reliability <= 1",
            name=op.f("ck_player_match_predictions_reliability_range"),
        ),
        sa.ForeignKeyConstraint(
            ["match_id"], ["matches.id"], name=op.f("fk_player_match_predictions_match_id_matches")
        ),
        sa.ForeignKeyConstraint(
            ["model_version_id"],
            ["model_versions.id"],
            name=op.f("fk_player_match_predictions_model_version_id_model_versions"),
        ),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["players.id"],
            name=op.f("fk_player_match_predictions_player_id_players"),
        ),
        sa.ForeignKeyConstraint(
            ["prediction_run_id"],
            ["prediction_runs.id"],
            name=op.f("fk_player_match_predictions_prediction_run_id_prediction_runs"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_player_match_predictions")),
        sa.UniqueConstraint(
            "prediction_run_id",
            "match_id",
            "player_id",
            "target",
            name=op.f("uq_player_match_predictions_prediction_run_id"),
        ),
    )
    op.create_table(
        "player_match_stats",
        sa.Column("match_id", sa.UUID(), nullable=False),
        sa.Column("team_id", sa.UUID(), nullable=False),
        sa.Column("player_id", sa.UUID(), nullable=False),
        sa.Column("minutes", sa.SmallInteger(), nullable=False),
        sa.Column("started", sa.Boolean(), nullable=False),
        sa.Column("football_position", sa.String(length=32), nullable=True),
        sa.Column("stats", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("ingestion_run_id", sa.UUID(), nullable=False),
        sa.Column("schema_version_id", sa.UUID(), nullable=True),
        sa.Column("source_record_id", sa.String(length=512), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("field_provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "minutes >= 0 AND minutes <= 130", name=op.f("ck_player_match_stats_valid_minutes")
        ),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["ingestion_runs.id"],
            name=op.f("fk_player_match_stats_ingestion_run_id_ingestion_runs"),
        ),
        sa.ForeignKeyConstraint(
            ["match_id"], ["matches.id"], name=op.f("fk_player_match_stats_match_id_matches")
        ),
        sa.ForeignKeyConstraint(
            ["player_id"], ["players.id"], name=op.f("fk_player_match_stats_player_id_players")
        ),
        sa.ForeignKeyConstraint(
            ["schema_version_id"],
            ["schema_versions.id"],
            name=op.f("fk_player_match_stats_schema_version_id_schema_versions"),
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["data_sources.id"],
            name=op.f("fk_player_match_stats_source_id_data_sources"),
        ),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], name=op.f("fk_player_match_stats_team_id_teams")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_player_match_stats")),
        sa.UniqueConstraint(
            "source_id", "source_record_id", name=op.f("uq_player_match_stats_source_id")
        ),
    )
    op.create_index(
        "ix_player_stats_match_player",
        "player_match_stats",
        ["match_id", "player_id"],
        unique=False,
    )
    op.create_table(
        "shots",
        sa.Column("match_id", sa.UUID(), nullable=False),
        sa.Column("team_id", sa.UUID(), nullable=False),
        sa.Column("player_id", sa.UUID(), nullable=False),
        sa.Column("assister_id", sa.UUID(), nullable=True),
        sa.Column("minute", sa.SmallInteger(), nullable=True),
        sa.Column("x", sa.Float(), nullable=True),
        sa.Column("y", sa.Float(), nullable=True),
        sa.Column("xg", sa.Float(), nullable=True),
        sa.Column("result", sa.String(length=64), nullable=True),
        sa.Column("situation", sa.String(length=64), nullable=True),
        sa.Column("body_part", sa.String(length=64), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("ingestion_run_id", sa.UUID(), nullable=False),
        sa.Column("schema_version_id", sa.UUID(), nullable=True),
        sa.Column("source_record_id", sa.String(length=512), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("field_provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["assister_id"], ["players.id"], name=op.f("fk_shots_assister_id_players")
        ),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["ingestion_runs.id"],
            name=op.f("fk_shots_ingestion_run_id_ingestion_runs"),
        ),
        sa.ForeignKeyConstraint(
            ["match_id"], ["matches.id"], name=op.f("fk_shots_match_id_matches")
        ),
        sa.ForeignKeyConstraint(
            ["player_id"], ["players.id"], name=op.f("fk_shots_player_id_players")
        ),
        sa.ForeignKeyConstraint(
            ["schema_version_id"],
            ["schema_versions.id"],
            name=op.f("fk_shots_schema_version_id_schema_versions"),
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["data_sources.id"], name=op.f("fk_shots_source_id_data_sources")
        ),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], name=op.f("fk_shots_team_id_teams")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_shots")),
        sa.UniqueConstraint("source_id", "source_record_id", name=op.f("uq_shots_source_id")),
    )
    op.create_table(
        "simulation_runs",
        sa.Column("prediction_run_id", sa.UUID(), nullable=False),
        sa.Column("league_id", sa.UUID(), nullable=True),
        sa.Column("simulation_count", sa.Integer(), nullable=False),
        sa.Column("seed", sa.BigInteger(), nullable=True),
        sa.Column("scoring_rule_version", sa.Integer(), nullable=True),
        sa.Column("parameters", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["league_id"], ["leagues.id"], name=op.f("fk_simulation_runs_league_id_leagues")
        ),
        sa.ForeignKeyConstraint(
            ["prediction_run_id"],
            ["prediction_runs.id"],
            name=op.f("fk_simulation_runs_prediction_run_id_prediction_runs"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_simulation_runs")),
    )
    op.create_table(
        "team_match_stats",
        sa.Column("match_id", sa.UUID(), nullable=False),
        sa.Column("team_id", sa.UUID(), nullable=False),
        sa.Column("opponent_team_id", sa.UUID(), nullable=False),
        sa.Column("is_home", sa.Boolean(), nullable=False),
        sa.Column("stats", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("ingestion_run_id", sa.UUID(), nullable=False),
        sa.Column("schema_version_id", sa.UUID(), nullable=True),
        sa.Column("source_record_id", sa.String(length=512), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("field_provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["ingestion_runs.id"],
            name=op.f("fk_team_match_stats_ingestion_run_id_ingestion_runs"),
        ),
        sa.ForeignKeyConstraint(
            ["match_id"], ["matches.id"], name=op.f("fk_team_match_stats_match_id_matches")
        ),
        sa.ForeignKeyConstraint(
            ["opponent_team_id"],
            ["teams.id"],
            name=op.f("fk_team_match_stats_opponent_team_id_teams"),
        ),
        sa.ForeignKeyConstraint(
            ["schema_version_id"],
            ["schema_versions.id"],
            name=op.f("fk_team_match_stats_schema_version_id_schema_versions"),
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["data_sources.id"],
            name=op.f("fk_team_match_stats_source_id_data_sources"),
        ),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], name=op.f("fk_team_match_stats_team_id_teams")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_team_match_stats")),
        sa.UniqueConstraint(
            "source_id", "source_record_id", name=op.f("uq_team_match_stats_source_id")
        ),
    )
    op.create_index(
        "ix_team_stats_match_team", "team_match_stats", ["match_id", "team_id"], unique=False
    )
    op.create_table(
        "fantasy_teams",
        sa.Column("league_id", sa.UUID(), nullable=False),
        sa.Column("member_id", sa.UUID(), nullable=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("is_user_team", sa.Boolean(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["league_id"], ["leagues.id"], name=op.f("fk_fantasy_teams_league_id_leagues")
        ),
        sa.ForeignKeyConstraint(
            ["member_id"],
            ["league_members.id"],
            name=op.f("fk_fantasy_teams_member_id_league_members"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fantasy_teams")),
        sa.UniqueConstraint("league_id", "name", name=op.f("uq_fantasy_teams_league_id")),
    )
    op.create_table(
        "budgets",
        sa.Column("fantasy_team_id", sa.UUID(), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_credits", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("remaining_credits", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["fantasy_team_id"],
            ["fantasy_teams.id"],
            name=op.f("fk_budgets_fantasy_team_id_fantasy_teams"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_budgets")),
        sa.UniqueConstraint(
            "fantasy_team_id", "effective_at", name=op.f("uq_budgets_fantasy_team_id")
        ),
    )
    op.create_table(
        "lineup_recommendations",
        sa.Column("simulation_run_id", sa.UUID(), nullable=False),
        sa.Column("league_id", sa.UUID(), nullable=False),
        sa.Column("fantasy_team_id", sa.UUID(), nullable=False),
        sa.Column("risk_mode", sa.String(length=24), nullable=False),
        sa.Column("formation", sa.String(length=64), nullable=False),
        sa.Column("starters", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("bench", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("expected_score", sa.Float(), nullable=False),
        sa.Column("median_score", sa.Float(), nullable=False),
        sa.Column("p10_score", sa.Float(), nullable=False),
        sa.Column("p90_score", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("objective_value", sa.Float(), nullable=False),
        sa.Column("data_cutoff", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["fantasy_team_id"],
            ["fantasy_teams.id"],
            name=op.f("fk_lineup_recommendations_fantasy_team_id_fantasy_teams"),
        ),
        sa.ForeignKeyConstraint(
            ["league_id"], ["leagues.id"], name=op.f("fk_lineup_recommendations_league_id_leagues")
        ),
        sa.ForeignKeyConstraint(
            ["simulation_run_id"],
            ["simulation_runs.id"],
            name=op.f("fk_lineup_recommendations_simulation_run_id_simulation_runs"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lineup_recommendations")),
    )
    op.create_table(
        "market_recommendations",
        sa.Column("simulation_run_id", sa.UUID(), nullable=False),
        sa.Column("league_id", sa.UUID(), nullable=False),
        sa.Column("fantasy_team_id", sa.UUID(), nullable=False),
        sa.Column("target_player_id", sa.UUID(), nullable=False),
        sa.Column("replace_player_id", sa.UUID(), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("horizon", sa.Integer(), nullable=False),
        sa.Column("expected_improvement", sa.Float(), nullable=False),
        sa.Column("value_over_replacement", sa.Float(), nullable=False),
        sa.Column("budget_efficiency", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("detail", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["fantasy_team_id"],
            ["fantasy_teams.id"],
            name=op.f("fk_market_recommendations_fantasy_team_id_fantasy_teams"),
        ),
        sa.ForeignKeyConstraint(
            ["league_id"], ["leagues.id"], name=op.f("fk_market_recommendations_league_id_leagues")
        ),
        sa.ForeignKeyConstraint(
            ["replace_player_id"],
            ["players.id"],
            name=op.f("fk_market_recommendations_replace_player_id_players"),
        ),
        sa.ForeignKeyConstraint(
            ["simulation_run_id"],
            ["simulation_runs.id"],
            name=op.f("fk_market_recommendations_simulation_run_id_simulation_runs"),
        ),
        sa.ForeignKeyConstraint(
            ["target_player_id"],
            ["players.id"],
            name=op.f("fk_market_recommendations_target_player_id_players"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_market_recommendations")),
    )
    op.create_table(
        "matchups",
        sa.Column("league_id", sa.UUID(), nullable=False),
        sa.Column("matchweek", sa.SmallInteger(), nullable=False),
        sa.Column("home_fantasy_team_id", sa.UUID(), nullable=False),
        sa.Column("away_fantasy_team_id", sa.UUID(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["away_fantasy_team_id"],
            ["fantasy_teams.id"],
            name=op.f("fk_matchups_away_fantasy_team_id_fantasy_teams"),
        ),
        sa.ForeignKeyConstraint(
            ["home_fantasy_team_id"],
            ["fantasy_teams.id"],
            name=op.f("fk_matchups_home_fantasy_team_id_fantasy_teams"),
        ),
        sa.ForeignKeyConstraint(
            ["league_id"], ["leagues.id"], name=op.f("fk_matchups_league_id_leagues")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_matchups")),
        sa.UniqueConstraint(
            "league_id", "matchweek", "home_fantasy_team_id", name=op.f("uq_matchups_league_id")
        ),
    )
    op.create_table(
        "roster_entries",
        sa.Column("fantasy_team_id", sa.UUID(), nullable=False),
        sa.Column("player_id", sa.UUID(), nullable=False),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("purchase_price", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("imported_name", sa.String(length=256), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["fantasy_team_id"],
            ["fantasy_teams.id"],
            name=op.f("fk_roster_entries_fantasy_team_id_fantasy_teams"),
        ),
        sa.ForeignKeyConstraint(
            ["player_id"], ["players.id"], name=op.f("fk_roster_entries_player_id_players")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_roster_entries")),
        sa.UniqueConstraint(
            "fantasy_team_id", "player_id", name=op.f("uq_roster_entries_fantasy_team_id")
        ),
    )



def downgrade() -> None:

    op.drop_table("roster_entries")
    op.drop_table("matchups")
    op.drop_table("market_recommendations")
    op.drop_table("lineup_recommendations")
    op.drop_table("budgets")
    op.drop_table("fantasy_teams")
    op.drop_index("ix_team_stats_match_team", table_name="team_match_stats")
    op.drop_table("team_match_stats")
    op.drop_table("simulation_runs")
    op.drop_table("shots")
    op.drop_index("ix_player_stats_match_player", table_name="player_match_stats")
    op.drop_table("player_match_stats")
    op.drop_table("player_match_predictions")
    op.drop_table("player_fantasy_roles")
    op.drop_index("ix_odds_match_available", table_name="odds_snapshots")
    op.drop_table("odds_snapshots")
    op.drop_table("market_entries")
    op.drop_table("lineups")
    op.drop_table("league_rules")
    op.drop_table("league_members")
    op.drop_index("ix_events_match_period_second", table_name="events")
    op.drop_table("events")
    op.drop_table("transfers")
    op.drop_table("suspensions")
    op.drop_index("ix_raw_objects_ingestion_run", table_name="raw_objects")
    op.drop_table("raw_objects")
    op.drop_index("ix_matches_kickoff", table_name="matches")
    op.drop_table("matches")
    op.drop_table("leagues")
    op.drop_table("injuries")
    op.drop_index("ix_quality_run_severity", table_name="data_quality_issues")
    op.drop_table("data_quality_issues")
    op.drop_table("seasons")
    op.drop_table("schema_versions")
    op.drop_index("ix_provider_entity_canonical", table_name="provider_entity_map")
    op.drop_table("provider_entity_map")
    op.drop_table("prediction_runs")
    op.drop_table("player_team_periods")
    op.drop_table("ingestion_runs")
    op.drop_table("venues")
    op.drop_table("users")
    op.drop_index(op.f("ix_teams_normalized_name"), table_name="teams")
    op.drop_table("teams")
    op.drop_index(op.f("ix_referees_normalized_name"), table_name="referees")
    op.drop_table("referees")
    op.drop_index("ix_explanation_owner", table_name="recommendation_explanations")
    op.drop_table("recommendation_explanations")
    op.drop_index("ix_players_identity", table_name="players")
    op.drop_table("players")
    op.drop_table("model_versions")
    op.drop_table("feature_snapshot_metadata")
    op.drop_table("data_sources")
    op.drop_table("competitions")
    op.drop_index(op.f("ix_coaches_normalized_name"), table_name="coaches")
    op.drop_table("coaches")
    op.drop_table("background_jobs")
