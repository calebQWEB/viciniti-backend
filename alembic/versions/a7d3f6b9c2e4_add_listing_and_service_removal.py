"""add admin removal fields to listings and services

Revision ID: a7d3f6b9c2e4
Revises: f1b4d8e2a6c3
Create Date: 2026-10-23 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a7d3f6b9c2e4'
down_revision: Union[str, Sequence[str], None] = 'f1b4d8e2a6c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ('listings', 'services')


def upgrade() -> None:
    for table in TABLES:
        op.add_column(table, sa.Column('removed_at', sa.DateTime(), nullable=True))
        op.add_column(table, sa.Column('removed_by', postgresql.UUID(as_uuid=True), nullable=True))
        op.add_column(table, sa.Column('removal_reason', sa.String(), nullable=True))
        op.create_foreign_key(f'{table}_removed_by_fkey', table, 'users', ['removed_by'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    for table in TABLES:
        op.drop_constraint(f'{table}_removed_by_fkey', table, type_='foreignkey')
        for column in ('removal_reason', 'removed_by', 'removed_at'):
            op.drop_column(table, column)
