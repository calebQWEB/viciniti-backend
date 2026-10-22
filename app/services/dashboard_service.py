from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload
from app.models.booking import Booking, BookingStatus
from app.models.listing import Listing, ListingStatus
from app.models.order import Order, OrderStatus
from app.models.notification import Notification, NotificationType
from app.models.message import Message
from uuid import UUID


def get_dashboard_stats(db: Session, user_id) -> dict:
    uid = UUID(str(user_id))

    balance = (
        db.query(func.coalesce(func.sum(Order.amount - Order.fee), 0))
        .filter(
            Order.seller_id == uid,
            Order.status == OrderStatus.completed,
            Order.payout_completed_at.is_(None),
        )
        .scalar()
    )
    active_listings = db.query(Listing).filter(
        Listing.user_id == uid,
        Listing.status == ListingStatus.active,
    ).count()
    pending_orders = db.query(Order).filter(
        or_(Order.buyer_id == uid, Order.seller_id == uid),
        Order.status.in_((OrderStatus.pending, OrderStatus.paid, OrderStatus.fulfilled)),
    ).count()
    unread_messages = db.query(Message).filter(
        Message.receiver_id == uid,
        Message.read.is_(False),
    ).count()

    return {
        "balance": float(balance),
        "active_listings": active_listings,
        "pending_orders": pending_orders,
        "unread_messages": unread_messages,
    }


def get_unpaid_bookings(db: Session, user_id: str):
    bookings = (
        db.query(Booking)
        .join(Order, Booking.order_id == Order.id)
        .options(joinedload(Booking.service), joinedload(Booking.provider))
        .filter(
            Booking.client_id == user_id,
            Booking.status == BookingStatus.confirmed,
            Order.status == OrderStatus.pending,
        )
        .all()
    )
    return [
        {
            "type": "booking_unpaid",
            "title": f"Payment needed for {b.service.title}",
            "subtitle": f"with {b.provider.name}",
            "link": f"/dashboard/bookings?tab=requests&highlight={b.id}",
            "count": None,
            "created_at": b.order.created_at,
        }
        for b in bookings
    ]

def get_booking_requests(db: Session, user_id: str):
    bookings = (
        db.query(Booking)
        .options(joinedload(Booking.service), joinedload(Booking.client))
        .filter(
            Booking.provider_id == user_id,
            Booking.status == BookingStatus.pending,
        )
        .all()
    )
    return [
        {
            "type": "booking_request",
            "title": f"New booking request for {b.service.title}",
            "subtitle": f"from {b.client.name}",
            "link": f"/dashboard/bookings?tab=requests&highlight={b.id}",
            "count": None,
            "created_at": b.created_at,
        }
        for b in bookings
    ]

def get_payout_blocked(db: Session, user_id: str):
    orders = (
        db.query(Order)
        .filter(
            Order.seller_id == user_id,
            Order.status == OrderStatus.completed,
            Order.payout_due_at.is_(None),
        )
        .all()
    )
    if not orders:
        return []
    return [{
        "type": "payout_blocked",
        "title": "Add a bank account to receive your payouts",
        "subtitle": f"{len(orders)} payout(s) waiting",
        "link": "/dashboard/profile?tab=payout",
        "count": len(orders),
        "created_at": min(o.completed_at for o in orders if o.completed_at),
    }]

def get_unread_messages(db: Session, user_id: str):
    unread = (
        db.query(Message)
        .filter(
            Message.receiver_id == user_id,
            Message.read.is_(False),
        )
        .all()
    )
    if not unread:
        return []

    sender_count = len({m.sender_id for m in unread})
    return [{
        "type": "unread_messages",
        "title": f"{len(unread)} unread message{'s' if len(unread) != 1 else ''}",
        "subtitle": f"from {sender_count} {'person' if sender_count == 1 else 'people'}",
        "link": "/dashboard/messages",
        "count": len(unread),
        "created_at": min(m.created_at for m in unread),
    }]

def _order_title(order: Order) -> str:
    """Listing orders use the listing title; service orders fall back to the service title."""
    if order.listing:
        return order.listing.title
    if order.service:
        return order.service.title
    return "your order"


def get_orders_to_complete(db: Session, user_id: UUID):
    """Seller side: buyer has paid, seller still needs to mark it complete."""
    orders = (
        db.query(Order)
        .options(
            joinedload(Order.listing),
            joinedload(Order.service),
            joinedload(Order.buyer),
        )
        .filter(
            Order.seller_id == user_id,
            Order.status == OrderStatus.paid,
        )
        .all()
    )
    return [
        {
            "type": "order_to_complete",
            "title": f"Mark {_order_title(o)} as complete",
            "subtitle": f"paid by {o.buyer.name}",
            "link": f"/dashboard/purchases?tab=sales&highlight={o.id}",
            "count": None,
            "created_at": o.created_at,
        }
        for o in orders
    ]


def get_orders_to_confirm(db: Session, user_id: UUID):
    """Buyer side: seller marked it complete, buyer still needs to confirm."""
    orders = (
        db.query(Order)
        .options(
            joinedload(Order.listing),
            joinedload(Order.service),
            joinedload(Order.seller),
        )
        .filter(
            Order.buyer_id == user_id,
            Order.status == OrderStatus.fulfilled,
        )
        .all()
    )
    return [
        {
            "type": "order_to_confirm",
            "title": f"Confirm you received {_order_title(o)}",
            "subtitle": f"from {o.seller.name}",
            "link": f"/dashboard/purchases?highlight={o.id}",
            "count": None,
            "created_at": o.completed_at or o.created_at,
        }
        for o in orders
    ]

ACTION_ITEMS_LIMIT = 5


def collect_action_items(db: Session, user_id) -> list:
    """All open action items, in priority order (oldest first within each type)."""
    user_id = UUID(str(user_id))

    items = []
    for fetch in (
        get_unpaid_bookings,
        get_booking_requests,
        get_orders_to_complete,
        get_orders_to_confirm,
        get_payout_blocked,
        get_unread_messages,
    ):
        group = fetch(db, user_id)
        group.sort(key=lambda item: item["created_at"])
        items.extend(group)
    return items


def get_action_items(db: Session, user_id) -> list:
    """Top items shown on the Overview page."""
    return collect_action_items(db, user_id)[:ACTION_ITEMS_LIMIT]

RECENT_ACTIVITY_LIMIT = 10

# Which open action item types "cover" each notification type
NOTIFICATION_COVERED_BY = {
    NotificationType.booking: {"booking_unpaid", "booking_request"},
    NotificationType.order: {"order_to_complete", "order_to_confirm"},
    NotificationType.message: {"unread_messages"},
    NotificationType.payout: {"payout_blocked"},
}


def get_recent_activity(db: Session, user_id):
    """Last 10 notifications, minus unread ones already represented in Needs Your Attention."""
    user_id = UUID(str(user_id))

    open_types = {item["type"] for item in collect_action_items(db, user_id)}
    hidden_types = [
        ntype
        for ntype, covering in NOTIFICATION_COVERED_BY.items()
        if covering & open_types
    ]

    query = db.query(Notification).filter(Notification.user_id == user_id)
    if hidden_types:
        # Keep: anything already read, anything untyped, anything of a type not covered
        query = query.filter(
            or_(
                Notification.read.is_(True),
                Notification.type.is_(None),
                Notification.type.notin_(hidden_types),
            )
        )
    return (
        query.order_by(Notification.created_at.desc())
        .limit(RECENT_ACTIVITY_LIMIT)
        .all()
    )

def get_badge_counts(db: Session, user_id) -> dict:
    uid = UUID(str(user_id))

    # My Purchases: buyer must confirm receipt + seller must mark complete
    to_confirm = db.query(func.count(Order.id)).filter(
        Order.buyer_id == uid,
        Order.status == OrderStatus.fulfilled,
    ).scalar()
    to_complete = db.query(func.count(Order.id)).filter(
        Order.seller_id == uid,
        Order.status == OrderStatus.paid,
    ).scalar()

    # My Bookings: unpaid confirmed bookings (as client) + pending requests (as provider)
    unpaid = (
        db.query(func.count(Booking.id))
        .join(Order, Booking.order_id == Order.id)
        .filter(
            Booking.client_id == uid,
            Booking.status == BookingStatus.confirmed,
            Order.status == OrderStatus.pending,
        )
        .scalar()
    )
    requests = db.query(func.count(Booking.id)).filter(
        Booking.provider_id == uid,
        Booking.status == BookingStatus.pending,
    ).scalar()

    messages = db.query(func.count(Message.id)).filter(
        Message.receiver_id == uid,
        Message.read.is_(False),
    ).scalar()

    notifications = db.query(func.count(Notification.id)).filter(
        Notification.user_id == uid,
        Notification.read.is_(False),
    ).scalar()

    # Profile: seller has completed orders with no payout scheduled (no bank account)
    payout_blocked = db.query(func.count(Order.id)).filter(
        Order.seller_id == uid,
        Order.status == OrderStatus.completed,
        Order.payout_due_at.is_(None),
    ).scalar()

    return {
        "purchases": to_confirm + to_complete,
        "bookings": unpaid + requests,
        "messages": messages,
        "notifications": notifications,
        "profile": payout_blocked,
    }

def get_getting_started(db: Session, user_id) -> dict:
    """First-run checklist for the dashboard: which setup steps the user has done."""
    from app.models.bank_account import BankAccount
    from app.models.service import Service
    from app.models.user import User

    uid = UUID(str(user_id))
    user = db.query(User).filter(User.id == uid).first()

    has_listing = db.query(Listing.id).filter(Listing.user_id == uid).first() is not None
    has_service = db.query(Service.id).filter(Service.user_id == uid).first() is not None

    return {
        "has_location": user.latitude is not None and user.longitude is not None,
        "has_avatar": bool(user.avatar),
        "has_payout_account": db.query(BankAccount.id).filter(BankAccount.user_id == uid).first() is not None,
        "has_listing_or_service": has_listing or has_service,
    }
