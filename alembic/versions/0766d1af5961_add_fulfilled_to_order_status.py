"""add_fulfilled_to_order_status

Revision ID: 0766d1af5961
Revises: a8d89186a33e
Create Date: 2026-07-02 11:33:24.232232

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0766d1af5961'
down_revision: Union[str, Sequence[str], None] = 'a8d89186a33e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE orderstatus ADD VALUE 'fulfilled' AFTER 'paid'")


def downgrade() -> None:
    pass