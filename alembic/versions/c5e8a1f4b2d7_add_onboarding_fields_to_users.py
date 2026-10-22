"""add onboarding fields to users

Revision ID: c5e8a1f4b2d7
Revises: 2207da7d2a04
Create Date: 2026-10-22 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c5e8a1f4b2d7'
down_revision: Union[str, Sequence[str], None] = '2207da7d2a04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('intent', sa.String(), nullable=True))
    op.add_column('users', sa.Column('onboarded_at', sa.DateTime(), nullable=True))
    # Existing accounts predate the welcome flow, so treat them as already onboarded
    op.execute("UPDATE users SET onboarded_at = created_at WHERE onboarded_at IS NULL")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'onboarded_at')
    op.drop_column('users', 'intent')
