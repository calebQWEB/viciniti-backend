"""update service images to ARRAY JSON

Revision ID: dbfb6d480104
Revises: 162189198973
Create Date: 2026-03-19 09:21:30.456519

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'dbfb6d480104'
down_revision: Union[str, Sequence[str], None] = '162189198973'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None



def upgrade() -> None:
    op.execute("""
        ALTER TABLE services
        ALTER COLUMN images TYPE JSON[]
        USING images::json[]
    """)
    # ### end Alembic commands ###



def downgrade() -> None:
    op.execute("""
        ALTER TABLE services
        ALTER COLUMN images TYPE VARCHAR[]
        USING images::varchar[]
    """)
    # ### end Alembic commands ###
