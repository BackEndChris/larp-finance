"""remove simulation valuation date default

Revision ID: e668f05105cb
Revises: b69f3a20ccf0
Create Date: 2026-11-07 17:40:16.373592

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e668f05105cb'
down_revision: Union[str, Sequence[str], None] = 'b69f3a20ccf0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
    "simulations",
    "valuation_date",
    server_default=None,
    existing_type=sa.Date(),
    existing_nullable=False,
)


def downgrade() -> None:
    op.alter_column(
    "simulations",
    "valuation_date",
    server_default=sa.text("CURRENT_DATE"),
    existing_type=sa.Date(),
    existing_nullable=False,
)
