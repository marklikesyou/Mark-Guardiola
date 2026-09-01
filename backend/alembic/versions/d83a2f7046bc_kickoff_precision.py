import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d83a2f7046bc"
down_revision = "b6a1739e4c20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "matches",
        sa.Column("kickoff_precision", sa.String(16), nullable=False, server_default="unknown"),
    )
    op.add_column(
        "matches",
        sa.Column(
            "kickoff_provenance",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_check_constraint(
        "kickoff_precision", "matches", "kickoff_precision IN ('unknown', 'date', 'minute')"
    )
    op.alter_column("matches", "kickoff_precision", server_default=None)
    op.alter_column("matches", "kickoff_provenance", server_default=None)


def downgrade() -> None:
    op.drop_constraint("kickoff_precision", "matches", type_="check")
    op.drop_column("matches", "kickoff_provenance")
    op.drop_column("matches", "kickoff_precision")
