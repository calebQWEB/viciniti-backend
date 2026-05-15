from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException, status
from app.models.order import Order, OrderStatus
from app.models.listing import Listing, ListingStatus
from app.schemas.order import OrderCreate, OrderUpdate
from app.services.notification_service import create_notification
from app.services.email_service import send_order_completed_email
from app.models.user import User
from uuid import UUID

# Viciniti's transaction fee percentage
FEE_PERCENTAGE = 0.05  # 5%

def create_order(db: Session, order_data: OrderCreate, buyer_id: UUID):
    # Get the listing
    listing = db.query(Listing).filter(Listing.id == order_data.listing_id).first()
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
    fee = round(amount * FEE_PERCENTAGE, 2)

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

def get_buyer_orders(db: Session, buyer_id: UUID):
    return (
        db.query(Order)
        .options(joinedload(Order.listing))
        .filter(Order.buyer_id == UUID(str(buyer_id)))
        .order_by(Order.created_at.desc())
        .all()
    )

def get_seller_orders(db: Session, seller_id: UUID):
    return (
        db.query(Order)
        .options(joinedload(Order.listing))
        .filter(Order.seller_id == UUID(str(seller_id)))
        .order_by(Order.created_at.desc())
        .all()
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