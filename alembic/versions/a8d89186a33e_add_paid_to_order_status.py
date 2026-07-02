"""add_paid_to_order_status

Revision ID: a8d89186a33e
Revises: 50c20a752350
Create Date: 2026-07-02 10:32:51.638993

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a8d89186a33e'
down_revision: Union[str, Sequence[str], None] = '50c20a752350'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE orderstatus ADD VALUE 'paid' AFTER 'pending'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values natively.
    # To roll back, you would need to recreate the enum without 'paid'.
    # This is left as a no-op to avoid data loss.
    pass