"""add_refunded_to_order_status

Revision ID: 9c9c3ba0efba
Revises: 1f17a600e59b
Create Date: 2026-07-06 10:34:52.657107

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9c9c3ba0efba'
down_revision: Union[str, Sequence[str], None] = '1f17a600e59b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE orderstatus ADD VALUE 'refunded' AFTER 'disputed'")


def downgrade() -> None:
    pass