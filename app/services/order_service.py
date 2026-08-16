from sqlalchemy.orm import Session, joinedload
from sqlalchemy import cast, String
from sqlalchemy import func
from fastapi import HTTPException, status
from math import ceil
from app.models.order import Order, OrderStatus
from app.models.listing import Listing, ListingStatus
from app.schemas.order import OrderCreate, OrderUpdate
from app.services.notification_service import create_notification
from app.services.email_service import send_order_completed_email
from app.models.user import User
from app.config import PLATFORM_FEE_PERCENTAGE
from uuid import UUID
from typing import Optional

def create_order(db: Session, order_data: OrderCreate, buyer_id: UUID):
    # Get the listing
    listing = db.query(Listing).filter(Listing.id == order_data.listing_id).with_for_update().first()
    if not listing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Listing not found"
        )

    # Prevent buying your own listing
    if listing.user_id == UUID(str(buyer_id)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot buy your own listing"
        )

    # Check listing is still active
    if listing.status != ListingStatus.active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This listing is no longer available"
        )

    # Calculate amount and fee
    amount = listing.price
    fee = round(amount * PLATFORM_FEE_PERCENTAGE, 2)

    new_order = Order(
        listing_id=order_data.listing_id,
        buyer_id=UUID(str(buyer_id)),
        seller_id=listing.user_id,
        amount=amount,
        fee=fee,
    )

    db.add(new_order)
    db.commit()
    db.refresh(new_order)

    return new_order


def _paginate_orders(
    db: Session,
    base_filter,
    page: int,
    limit: int,
    search: Optional[str],
    status_filter: Optional[str],
):
    query = (
    db.query(Order)
    .options(
        joinedload(Order.listing),
        joinedload(Order.service),
        joinedload(Order.buyer),
        joinedload(Order.seller),
    )
    .filter(base_filter)
)

    if status_filter and status_filter != "all":
        try:
            status_enum = OrderStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status filter: {status_filter}"
            )
        query = query.filter(Order.status == status_enum)

    if search:
        # Order.id is a UUID column -- cast to text so partial/substring
        # matches work the same way the old client-side search did.
        query = query.filter(cast(Order.id, String).ilike(f"%{search}%"))

    total = query.count()

    items = (
        query.order_by(Order.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )

    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": max(1, ceil(total / limit)) if total else 1,
    }


def get_buyer_orders(
    db: Session,
    buyer_id: UUID,
    page: int = 1,
    limit: int = 10,
    search: Optional[str] = None,
    status_filter: Optional[str] = None,
):
    return _paginate_orders(
        db,
        Order.buyer_id == UUID(str(buyer_id)),
        page,
        limit,
        search,
        status_filter,
    )


def get_seller_orders(
    db: Session,
    seller_id: UUID,
    page: int = 1,
    limit: int = 10,
    search: Optional[str] = None,
    status_filter: Optional[str] = None,
):
    return _paginate_orders(
        db,
        Order.seller_id == UUID(str(seller_id)),
        page,
        limit,
        search,
        status_filter,
    )

def get_order(db: Session, order_id: UUID):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )
    return order

def update_order(db: Session, order_id: UUID, order_data: OrderUpdate, user_id: UUID):
    order = get_order(db, order_id)

    # Only buyer or seller can update the order
    if order.buyer_id != UUID(str(user_id)) and order.seller_id != UUID(str(user_id)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to update this order"
        )

    for field, value in order_data.model_dump(exclude_unset=True).items():
        setattr(order, field, value)

    db.commit()
    db.refresh(order)

    # Send order completed email to buyer when seller marks as complete
    if order_data.status and order_data.status.value == "completed":
        buyer = db.query(User).filter(User.id == order.buyer_id).first()

        if buyer:
            send_order_completed_email(
                to=buyer.email,
                name=buyer.name,
                order_id=str(order.id)
            )

            # Also notify buyer in-app
            create_notification(
                db,
                buyer.id,
                f"Your order #{str(order.id)[:8].upper()} has been completed!"
            )

    return order

def cancel_order(db: Session, order_id: UUID, user_id: UUID):
    """Cancel a pending order. Only the buyer can cancel their own orders."""
    order = get_order(db, order_id)

    # Only buyer can cancel their own order
    if order.buyer_id != UUID(str(user_id)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only cancel your own orders"
        )

    # Can only cancel pending orders
    if order.status != OrderStatus.pending:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel {order.status.value} order"
        )

    order.status = OrderStatus.cancelled
    db.commit()
    db.refresh(order)

    return order

def get_order_status_counts(db: Session, user_id: UUID, filter_field):
    rows = (
        db.query(Order.status, func.count(Order.id))
        .filter(filter_field == UUID(str(user_id)))
        .group_by(Order.status)
        .all()
    )
    counts = {s.value: 0 for s in OrderStatus}
    for status_val, count in rows:
        counts[status_val.value] = count
    counts["all"] = sum(counts.values())
    return counts