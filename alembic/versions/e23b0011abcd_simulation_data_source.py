"""Preserve simulation data provenance and selected trading dates."""
from alembic import op
import sqlalchemy as sa

revision = "e23b0011abcd"
down_revision = "d22a0010abcd"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("simulations", sa.Column("data_source", sa.String(30), nullable=False, server_default="demo"))
    op.add_column("simulations", sa.Column("actual_purchase_date", sa.Date(), nullable=True))
    op.add_column("simulations", sa.Column("actual_valuation_date", sa.Date(), nullable=True))
    op.add_column("simulations", sa.Column("retry_not_before", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("simulations", "retry_not_before")
    op.drop_column("simulations", "actual_valuation_date")
    op.drop_column("simulations", "actual_purchase_date")
    op.drop_column("simulations", "data_source")
