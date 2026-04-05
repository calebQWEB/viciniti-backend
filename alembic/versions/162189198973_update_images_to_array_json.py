"""update images to ARRAY JSON

Revision ID: 162189198973
Revises: 
Create Date: 2026-03-18 20:14:04.512470

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '162189198973'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE listings 
        ALTER COLUMN images TYPE JSON[] 
        USING images::json[]
    """)

def downgrade() -> None:
    op.execute("""
        ALTER TABLE listings 
        ALTER COLUMN images TYPE VARCHAR[] 
        USING images::varchar[]
    """)
    # ### end Alembic commands ###
