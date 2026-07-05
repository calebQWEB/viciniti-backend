"""create_reviews_table

Revision ID: 9a87471cb075
Revises: 60400fd75e17
Create Date: 2026-07-04 11:56:40.141384

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = '9a87471cb075'
down_revision: Union[str, Sequence[str], None] = '60400fd75e17'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'reviews',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('order_id', UUID(as_uuid=True), sa.ForeignKey('orders.id'), nullable=False, unique=True),
        sa.Column('buyer_id', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('seller_id', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('rating', sa.Integer(), nullable=False),
        sa.Column('review_text', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('reviews')