"""add user suspension fields

Revision ID: f1b4d8e2a6c3
Revises: e3a7c1d9f5b2
Create Date: 2026-10-23 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f1b4d8e2a6c3'
down_revision: Union[str, Sequence[str], None] = 'e3a7c1d9f5b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('is_suspended', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('users', sa.Column('suspended_at', sa.DateTime(), nullable=True))
    op.add_column('users', sa.Column('suspended_by', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('users', sa.Column('suspension_reason', sa.String(), nullable=True))
    op.add_column('users', sa.Column('suspension_note', sa.Text(), nullable=True))
    op.create_foreign_key('users_suspended_by_fkey', 'users', 'users', ['suspended_by'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    op.drop_constraint('users_suspended_by_fkey', 'users', type_='foreignkey')
    for column in ('suspension_note', 'suspension_reason', 'suspended_by', 'suspended_at', 'is_suspended'):
        op.drop_column('users', column)
