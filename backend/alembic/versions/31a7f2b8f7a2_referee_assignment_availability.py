import sqlalchemy as sa
from alembic import op

revision = "31a7f2b8f7a2"
down_revision = "57d37e15ab90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("matches", sa.Column("referee_available_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("matches", "referee_available_at")
