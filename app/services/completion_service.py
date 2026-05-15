"""
Service completion and proof handling.

Handles completion photos, seller notes, and buyer confirmation.
Tracks evidence for chargeback defense.
"""

from sqlalchemy.orm import Session
from uuid import UUID
from datetime import datetime
from typing import List
from app.models.order import Order, OrderStatus
from app.models.user import User
from app.services.notification_service import create_notification


async def mark_order_completion(
    db: Session,
    order_id: UUID,
    seller_id: UUID,
    photos: List[str] = None,
    notes: str = None
) -> bool:
    """
    Seller marks order as completed with proof.
    
    Args:
        db: Database session
        order_id: Order ID
        seller_id: Seller user ID (for verification)
        photos: List of photo URLs showing completion
        notes: Description of what was completed
    
    Returns:
        True if successful, False if unauthorized or order not found
    """
    
    order = db.query(Order).filter(Order.id == order_id).first()
    
    if not order:
        print(f"❌ Order not found: {order_id}")
        return False
    
    # Verify seller ownership
    if order.seller_id != seller_id:
        print(f"❌ Unauthorized: User {seller_id} is not seller of order {order_id}")
        return False
    
    # Verify order is still pending
    if order.status != OrderStatus.pending:
        print(f"❌ Order {order_id} is not in pending status (current: {order.status})")
        return False
    
    # Store completion proof
    order.completion_photos = photos or []
    order.completion_notes = notes
    order.completed_at = datetime.utcnow()
    
    # Notify buyer to confirm completion
    buyer = db.query(User).filter(User.id == order.buyer_id).first()
    create_notification(
        db,
        order.buyer_id,
        f"✓ Your service is complete! Please review and confirm completion. "
        f"Service: {order.listing.title if order.listing else 'Order'}"
    )
    
    db.commit()
    
    print(f"✅ Order {order_id} marked as completed by seller {seller_id}")
    print(f"   Photos: {len(order.completion_photos or [])}")
    print(f"   Notes: {notes[:50] if notes else 'None'}...")
    
    return True


async def buyer_confirm_completion(
    db: Session,
    order_id: UUID,
    buyer_id: UUID,
    rating: int = None,
    review_text: str = None
) -> bool:
    """
    Buyer confirms order completion.
    
    This is critical for chargeback defense - proves buyer accepted the service.
    
    Args:
        db: Database session
        order_id: Order ID
        buyer_id: Buyer user ID (for verification)
        rating: Optional rating 1-5 stars
        review_text: Optional review text
    
    Returns:
        True if successful, False if unauthorized
    """
    
    order = db.query(Order).filter(Order.id == order_id).first()
    
    if not order:
        print(f"❌ Order not found: {order_id}")
        return False
    
    # Verify buyer ownership
    if order.buyer_id != buyer_id:
        print(f"❌ Unauthorized: User {buyer_id} is not buyer of order {order_id}")
        return False
    
    # Verify order has completion proof
    if not order.completed_at:
        print(f"❌ Order {order_id} is not marked as completed by seller yet")
        return False
    
    # Mark as confirmed
    order.buyer_accepted_at = datetime.utcnow()
    
    # NOTE: Order status stays as 'pending' until payment is released
    # This is intentional - marks it as "service delivered, awaiting payment release"
    
    # Notify seller that buyer confirmed
    create_notification(
        db,
        order.seller_id,
        f"✅ Payment confirmed! Buyer accepted completion of order {order_id}. "
        f"Payment of ₦{order.amount:,.0f} is now being released to your account."
    )
    
    # Notify buyer of confirmation
    create_notification(
        db,
        order.buyer_id,
        f"✅ Thank you for confirming completion! Your service is now complete."
    )
    
    db.commit()
    
    print(f"✅ Order {order_id} confirmed by buyer {buyer_id}")
    print(f"   Rating: {rating}/5" if rating else "   Rating: Not provided")
    print(f"   Review: {review_text[:50] if review_text else 'No review'}...")
    
    return True


def get_order_completion_evidence(
    db: Session,
    order_id: UUID
) -> dict:
    """
    Gather all completion evidence for an order.
    Used for chargeback defense.
    
    Returns dict with:
    - completion_photos: List of photo URLs
    - completion_notes: Seller's description
    - completed_at: When marked complete
    - buyer_accepted_at: When buyer confirmed
    - buyer_contact: Buyer's name/email for bank
    - service_details: What was purchased
    """
    
    order = db.query(Order).filter(Order.id == order_id).first()
    
    if not order:
        return None
    
    buyer = order.buyer
    
    evidence = {
        "order_id": str(order.id),
        "service": order.listing.title if order.listing else "Service",
        "seller_id": str(order.seller_id),
        "seller_name": order.seller.full_name if order.seller else "Unknown",
        "buyer_id": str(order.buyer_id),
        "buyer_name": buyer.full_name if buyer else "Unknown",
        "buyer_email": buyer.email if buyer else "Unknown",
        "amount": order.amount,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "completion": {
            "photos": order.completion_photos or [],
            "notes": order.completion_notes,
            "completed_at": order.completed_at.isoformat() if order.completed_at else None,
            "buyer_accepted_at": order.buyer_accepted_at.isoformat() if order.buyer_accepted_at else None,
            "buyer_confirmed": bool(order.buyer_accepted_at)
        }
    }
    
    return evidence
