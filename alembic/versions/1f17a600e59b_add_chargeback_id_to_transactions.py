"""add_chargeback_id_to_transactions

Revision ID: 1f17a600e59b
Revises: 9a87471cb075
Create Date: 2026-07-06 10:25:06.267746

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1f17a600e59b'
down_revision: Union[str, Sequence[str], None] = '9a87471cb075'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('transactions', sa.Column('chargeback_id', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('transactions', 'chargeback_id')