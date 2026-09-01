import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "57d37e15ab90"
down_revision = "519500e5295e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "team_standing_snapshots",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("source_id", sa.UUID(), sa.ForeignKey("data_sources.id"), nullable=False),
        sa.Column(
            "ingestion_run_id", sa.UUID(), sa.ForeignKey("ingestion_runs.id"), nullable=False
        ),
        sa.Column("schema_version_id", sa.UUID(), sa.ForeignKey("schema_versions.id")),
        sa.Column("source_record_id", sa.String(512), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("field_provenance", postgresql.JSONB(), nullable=False),
        sa.Column("team_id", sa.UUID(), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("season_id", sa.UUID(), sa.ForeignKey("seasons.id"), nullable=False),
        sa.Column("table_type", sa.String(64), nullable=False),
        *(
            sa.Column(name, sa.SmallInteger(), nullable=False)
            for name in (
                "rank",
                "played",
                "points",
                "won",
                "drawn",
                "lost",
                "goals_for",
                "goals_against",
            )
        ),
        sa.UniqueConstraint("source_id", "source_record_id"),
    )
    op.create_index(
        "ix_standings_team_available", "team_standing_snapshots", ["team_id", "available_at"]
    )


def downgrade() -> None:
    op.drop_table("team_standing_snapshots")
