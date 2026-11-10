"""Add durable simulation recovery state."""
from alembic import op
import sqlalchemy as sa

revision = "d22a0010abcd"
down_revision = "bc36a9082577"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("simulations", sa.Column("processing_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("simulations", sa.Column("dispatch_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("simulations", sa.Column("next_dispatch_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index("ix_simulations_recovery", "simulations", ["status", "next_dispatch_at"])


def downgrade():
    op.drop_index("ix_simulations_recovery", table_name="simulations")
    op.drop_column("simulations", "next_dispatch_at")
    op.drop_column("simulations", "dispatch_attempts")
    op.drop_column("simulations", "processing_attempts")
