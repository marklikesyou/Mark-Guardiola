import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b6a1739e4c20"
down_revision = "924b6e1d032a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "matches",
        sa.Column(
            "result_provenance",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column("player_team_periods", sa.Column("available_at", sa.DateTime(timezone=True)))
    op.add_column(
        "player_team_periods",
        sa.Column(
            "evidence", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
    )
    op.alter_column("matches", "result_provenance", server_default=None)
    op.alter_column("player_team_periods", "evidence", server_default=None)


def downgrade() -> None:
    op.drop_column("player_team_periods", "evidence")
    op.drop_column("player_team_periods", "available_at")
    op.drop_column("matches", "result_provenance")
