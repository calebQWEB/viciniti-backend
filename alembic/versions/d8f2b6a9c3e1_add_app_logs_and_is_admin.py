"""add app_logs table and users.is_admin

Revision ID: d8f2b6a9c3e1
Revises: c5e8a1f4b2d7
Create Date: 2026-10-22 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd8f2b6a9c3e1'
down_revision: Union[str, Sequence[str], None] = 'c5e8a1f4b2d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'users',
        sa.Column('is_admin', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    )

    # The app's startup (Base.metadata.create_all) may already have created this table
    # from the model, with the same columns and index names, before migrations ran
    if sa.inspect(op.get_bind()).has_table('app_logs'):
        return

    op.create_table(
        'app_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('level', sa.String(length=16), nullable=False),
        sa.Column('category', sa.String(length=32), nullable=False),
        sa.Column('event', sa.String(length=64), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('request_method', sa.String(length=8), nullable=True),
        sa.Column('request_path', sa.String(length=512), nullable=True),
        sa.Column('status_code', sa.Integer(), nullable=True),
        sa.Column('error_ref', sa.String(length=16), nullable=True),
        sa.Column('traceback', sa.Text(), nullable=True),
        sa.Column('alert_sent', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('resolved_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('resolution_note', sa.Text(), nullable=True),
    )
    op.create_index('ix_app_logs_created_at', 'app_logs', ['created_at'])
    op.create_index('ix_app_logs_level', 'app_logs', ['level'])
    op.create_index('ix_app_logs_category', 'app_logs', ['category'])
    op.create_index('ix_app_logs_event', 'app_logs', ['event'])
    op.create_index('ix_app_logs_error_ref', 'app_logs', ['error_ref'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_app_logs_error_ref', 'app_logs')
    op.drop_index('ix_app_logs_event', 'app_logs')
    op.drop_index('ix_app_logs_category', 'app_logs')
    op.drop_index('ix_app_logs_level', 'app_logs')
    op.drop_index('ix_app_logs_created_at', 'app_logs')
    op.drop_table('app_logs')
    op.drop_column('users', 'is_admin')
