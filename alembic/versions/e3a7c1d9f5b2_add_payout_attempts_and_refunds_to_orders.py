"""add payout attempt tracking and manual refund fields to orders

Revision ID: e3a7c1d9f5b2
Revises: d8f2b6a9c3e1
Create Date: 2026-10-23 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e3a7c1d9f5b2'
down_revision: Union[str, Sequence[str], None] = 'd8f2b6a9c3e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('orders', sa.Column('payout_attempts', sa.Integer(), nullable=False, server_default=sa.text('0')))
    op.add_column('orders', sa.Column('payout_last_attempt_at', sa.DateTime(), nullable=True))
    op.add_column('orders', sa.Column('payout_last_error', sa.String(), nullable=True))
    op.add_column('orders', sa.Column('refunded_at', sa.DateTime(), nullable=True))
    op.add_column('orders', sa.Column('refund_reference', sa.String(), nullable=True))
    op.add_column('orders', sa.Column('refund_note', sa.String(), nullable=True))
    op.add_column('orders', sa.Column('refunded_by', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key('orders_refunded_by_fkey', 'orders', 'users', ['refunded_by'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    op.drop_constraint('orders_refunded_by_fkey', 'orders', type_='foreignkey')
    for column in ('refunded_by', 'refund_note', 'refund_reference', 'refunded_at',
                   'payout_last_error', 'payout_last_attempt_at', 'payout_attempts'):
        op.drop_column('orders', column)
