"""add performance indexes

Revision ID: 796dd169357f
Revises: 109f3b7e4383
Create Date: 2026-03-31 09:51:10.508229

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '796dd169357f'
down_revision: Union[str, Sequence[str], None] = '109f3b7e4383'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # Users
    op.create_index("ix_users_email", "users", ["email"], if_not_exists=True)

    # Listings
    op.create_index("ix_listings_user_id", "listings", ["user_id"], if_not_exists=True)
    op.create_index("ix_listings_status", "listings", ["status"], if_not_exists=True)
    op.create_index("ix_listings_category", "listings", ["category"], if_not_exists=True)
    op.create_index("ix_listings_created_at", "listings", ["created_at"], if_not_exists=True)

    # Services
    op.create_index("ix_services_user_id", "services", ["user_id"], if_not_exists=True)
    op.create_index("ix_services_status", "services", ["status"], if_not_exists=True)
    op.create_index("ix_services_category", "services", ["category"], if_not_exists=True)
    op.create_index("ix_services_created_at", "services", ["created_at"], if_not_exists=True)

    # Orders
    op.create_index("ix_orders_buyer_id", "orders", ["buyer_id"], if_not_exists=True)
    op.create_index("ix_orders_seller_id", "orders", ["seller_id"], if_not_exists=True)
    op.create_index("ix_orders_status", "orders", ["status"], if_not_exists=True)
    op.create_index("ix_orders_created_at", "orders", ["created_at"], if_not_exists=True)

    # Bookings
    op.create_index("ix_bookings_client_id", "bookings", ["client_id"], if_not_exists=True)
    op.create_index("ix_bookings_provider_id", "bookings", ["provider_id"], if_not_exists=True)
    op.create_index("ix_bookings_status", "bookings", ["status"], if_not_exists=True)
    op.create_index("ix_bookings_created_at", "bookings", ["created_at"], if_not_exists=True)

    # Messages
    op.create_index("ix_messages_sender_id", "messages", ["sender_id"], if_not_exists=True)
    op.create_index("ix_messages_receiver_id", "messages", ["receiver_id"], if_not_exists=True)
    op.create_index("ix_messages_created_at", "messages", ["created_at"], if_not_exists=True)

    # Notifications
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"], if_not_exists=True)
    op.create_index("ix_notifications_read", "notifications", ["read"], if_not_exists=True)

    # Transactions
    op.create_index("ix_transactions_user_id", "transactions", ["user_id"], if_not_exists=True)
    op.create_index("ix_transactions_status", "transactions", ["status"], if_not_exists=True)
    op.create_index("ix_transactions_reference", "transactions", ["reference"], if_not_exists=True)


def downgrade():
    op.drop_index("ix_users_email", "users", if_exists=True)
    op.drop_index("ix_listings_user_id", "listings", if_exists=True)
    op.drop_index("ix_listings_status", "listings", if_exists=True)
    op.drop_index("ix_listings_category", "listings", if_exists=True)
    op.drop_index("ix_listings_created_at", "listings", if_exists=True)
    op.drop_index("ix_services_user_id", "services", if_exists=True)
    op.drop_index("ix_services_status", "services", if_exists=True)
    op.drop_index("ix_services_category", "services", if_exists=True)
    op.drop_index("ix_services_created_at", "services", if_exists=True)
    op.drop_index("ix_orders_buyer_id", "orders", if_exists=True)
    op.drop_index("ix_orders_seller_id", "orders", if_exists=True)
    op.drop_index("ix_orders_status", "orders", if_exists=True)
    op.drop_index("ix_orders_created_at", "orders", if_exists=True)
    op.drop_index("ix_bookings_client_id", "bookings", if_exists=True)
    op.drop_index("ix_bookings_provider_id", "bookings", if_exists=True)
    op.drop_index("ix_bookings_status", "bookings", if_exists=True)
    op.drop_index("ix_bookings_created_at", "bookings", if_exists=True)
    op.drop_index("ix_messages_sender_id", "messages", if_exists=True)
    op.drop_index("ix_messages_receiver_id", "messages", if_exists=True)
    op.drop_index("ix_messages_created_at", "messages", if_exists=True)
    op.drop_index("ix_notifications_user_id", "notifications", if_exists=True)
    op.drop_index("ix_notifications_read", "notifications", if_exists=True)
    op.drop_index("ix_transactions_user_id", "transactions", if_exists=True)
    op.drop_index("ix_transactions_status", "transactions", if_exists=True)
    op.drop_index("ix_transactions_reference", "transactions", if_exists=True)