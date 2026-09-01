import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a3470c38e122"
down_revision = "d83a2f7046bc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("players", sa.Column("photo_url", sa.Text()))
    op.add_column(
        "players",
        sa.Column(
            "photo_provenance",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_check_constraint(
        "photo_url_https", "players", "photo_url IS NULL OR photo_url LIKE 'https://%'"
    )
    op.alter_column("players", "photo_provenance", server_default=None)


def downgrade() -> None:
    op.drop_constraint("photo_url_https", "players", type_="check")
    op.drop_column("players", "photo_provenance")
    op.drop_column("players", "photo_url")
