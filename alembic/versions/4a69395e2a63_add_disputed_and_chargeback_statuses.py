"""Add disputed and chargeback statuses

Revision ID: 4a69395e2a63
Revises: 618602b8d78d
Create Date: 2026-05-26 14:54:00.440195

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4a69395e2a63'
down_revision: Union[str, Sequence[str], None] = '618602b8d78d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.execute("ALTER TYPE transactionstatus ADD VALUE IF NOT EXISTS 'chargeback_filed'")
    op.execute("ALTER TYPE transactionstatus ADD VALUE IF NOT EXISTS 'chargeback_won'")
    op.execute("ALTER TYPE transactionstatus ADD VALUE IF NOT EXISTS 'chargeback_lost'")
    op.execute("ALTER TYPE orderstatus ADD VALUE IF NOT EXISTS 'disputed'")



def downgrade() -> None:
    """Downgrade schema."""
    pass
