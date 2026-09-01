import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "924b6e1d032a"
down_revision = "31a7f2b8f7a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "prediction_runs",
        sa.Column(
            "simulation_priors", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'")
        ),
    )
    op.alter_column("prediction_runs", "simulation_priors", server_default=None)


def downgrade() -> None:
    op.drop_column("prediction_runs", "simulation_priors")
