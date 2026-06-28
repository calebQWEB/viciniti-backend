from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas import OrderCreate, OrderUpdate, OrderResponse
from app.services.order_service import (
    create_order, get_buyer_orders, get_seller_orders, get_order, update_order, cancel_order
)
from app.services.completion_service import (
    mark_order_completion, buyer_confirm_completion, get_order_completion_evidence
)
from app.utils.security import get_current_user
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel

router = APIRouter(prefix="/orders", tags=["orders"])

# Request/Response models for completion endpoints
class OrderCompletionRequest(BaseModel):
    photos: Optional[List[str]] = None
    notes: Optional[str] = None

class OrderConfirmationRequest(BaseModel):
    rating: Optional[int] = None  # 1-5 stars
    review: Optional[str] = None

# Create a new order
@router.post("/", response_model=OrderResponse)
def create(
    order_data: OrderCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return create_order(db, order_data, current_user["sub"])

# Get all orders where I am the buyer
@router.get("/my-purchases", response_model=List[OrderResponse])
def my_purchases(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return get_buyer_orders(db, current_user["sub"])

# Get all orders where I am the seller
@router.get("/my-sales", response_model=List[OrderResponse])
def my_sales(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return get_seller_orders(db, current_user["sub"])

# Get a single order by ID
@router.get("/{order_id}", response_model=OrderResponse)
def get_one(
    order_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return get_order(db, order_id)

# Update an order status
@router.put("/{order_id}", response_model=OrderResponse)
def update(
    order_id: UUID,
    order_data: OrderUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return update_order(db, order_id, order_data, current_user["sub"])

# Cancel a pending order
@router.delete("/{order_id}")
def delete(
    order_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    cancel_order(db, order_id, current_user["sub"])
    return {"status": "success", "message": "Order cancelled"}

# Seller marks order as completed (with photos and notes)
@router.post("/{order_id}/complete")
async def complete_order(
    order_id: UUID,
    completion_data: OrderCompletionRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Seller marks the order as completed and uploads proof.
    
    This creates evidence for chargeback defense.
    Requires: photos (at least one recommended), notes describing work done.
    """
    success = await mark_order_completion(
        db,
        order_id,
        UUID(current_user["sub"]),  # Convert string from JWT to UUID
        photos=completion_data.photos,
        notes=completion_data.notes
    )
    
    if not success:
        return {
            "status": "error",
            "message": "Could not mark order as complete. Check ownership and order status."
        }
    
    return {
        "status": "success",
        "message": "Order marked as complete. Buyer has been notified to confirm.",
        "order_id": str(order_id)
    }

# Buyer confirms order completion
@router.post("/{order_id}/confirm-completion")
async def confirm_order_completion(
    order_id: UUID,
    confirmation_data: OrderConfirmationRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Buyer confirms that the service was completed as expected.
    
    CRITICAL: This step creates evidence that proves buyer accepted the service.
    This is the strongest defense against chargebacks.
    """
    success = await buyer_confirm_completion(
        db,
        order_id,
        UUID(current_user["sub"]),  # Convert string from JWT to UUID
        rating=confirmation_data.rating,
        review_text=confirmation_data.review
    )
    
    if not success:
        return {
            "status": "error",
            "message": "Could not confirm completion. Check ownership or order status."
        }
    
    return {
        "status": "success",
        "message": "✅ Thank you! Completion confirmed. Seller payment is being processed.",
        "order_id": str(order_id)
    }

# Get completion evidence for chargeback defense
@router.get("/{order_id}/evidence")
def get_completion_evidence(
    order_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get all completion evidence for an order.
    Used for chargeback disputes.
    
    Only accessible to seller, buyer, or admin.
    """
    evidence = get_order_completion_evidence(db, order_id)
    
    if not evidence:
        return {"status": "error", "message": "Order not found"}
    
    # Verify access
    order = get_order(db, order_id)
    if order.seller_id != UUID(current_user["sub"]) and order.buyer_id != UUID(current_user["sub"]):
        return {
            "status": "error",
            "message": "Unauthorized - only seller and buyer can view evidence"
        }
    
    return {
        "status": "success",
        "evidence": evidence
    }


# Get dispute details for seller
@router.get("/{order_id}/dispute")
def get_dispute_details(
    order_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get chargeback/dispute details for an order.
    Only seller can view (they need this to respond).
    """
    from app.models.order import Order
    from app.models.transaction import Transaction
    
    order = db.query(Order).filter(Order.id == order_id).first()
    
    if not order:
        return {
            "status": "error",
            "message": "Order not found"
        }
    
    # Verify seller ownership
    if order.seller_id != UUID(current_user["sub"]):
        return {
            "status": "error",
            "message": "Unauthorized - only seller can view dispute"
        }
    
    # Get transaction with chargeback details
    transaction = db.query(Transaction).filter(
        Transaction.order_id == order_id
    ).first()
    
    print(f"🔍 Debug: Looking for transaction with order_id={order_id}")
    print(f"   Found transaction: {transaction}")
    if transaction:
        print(f"   Transaction ID: {transaction.id}")
        print(f"   Transaction status: {transaction.status}")
        print(f"   Chargeback filed at: {transaction.chargeback_filed_at}")
    
    if not transaction:
        return {
            "status": "error",
            "message": "No transaction found for this order"
        }
    
    # If no chargeback filed, return that info
    if not transaction.chargeback_filed_at:
        print(f"❌ No chargeback_filed_at value found")
        return {
            "status": "success",
            "dispute": None,
            "message": "No chargeback filed for this order"
        }
    
    # Get evidence
    evidence = get_order_completion_evidence(db, order_id)
    
    return {
        "status": "success",
        "dispute": {
            "transaction_id": str(transaction.id),
            "reference": transaction.reference,
            "amount": transaction.amount,
            "chargeback_status": transaction.status,
            "chargeback_reason": transaction.chargeback_reason,
            "chargeback_filed_at": transaction.chargeback_filed_at.isoformat() if transaction.chargeback_filed_at else None,
            "chargeback_resolved_at": transaction.chargeback_resolved_at.isoformat() if transaction.chargeback_resolved_at else None,
            "seller_response": transaction.chargeback_evidence_notes,
            "evidence_photos": transaction.chargeback_evidence_photos or [],
            "buyer_name": order.buyer.name if order.buyer else "Unknown",
            "listing_title": order.listing.title if order.listing else "Order"
        },
        "evidence": evidence
    }


# Add/update chargeback response
class ChargebackResponseRequest(BaseModel):
    response_notes: str  # Seller's defense/response
    evidence_photos: Optional[List[str]] = []  # Optional photo URLs


@router.post("/{order_id}/chargeback-response")
def add_chargeback_response(
    order_id: UUID,
    response_data: ChargebackResponseRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Seller submits additional evidence/response to chargeback.
    This response is sent to the bank as part of the dispute.
    """
    from app.models.order import Order
    from app.models.transaction import Transaction
    
    order = db.query(Order).filter(Order.id == order_id).first()
    
    if not order:
        return {
            "status": "error",
            "message": "Order not found"
        }
    
    # Verify seller ownership
    if order.seller_id != UUID(current_user["sub"]):
        return {
            "status": "error",
            "message": "Unauthorized - only seller can respond to dispute"
        }
    
    # Get transaction
    transaction = db.query(Transaction).filter(
        Transaction.order_id == order_id
    ).first()
    
    if not transaction:
        return {
            "status": "error",
            "message": "No transaction found for this order"
        }
    
    # Check if chargeback is filed
    if not transaction.chargeback_filed_at:
        return {
            "status": "error",
            "message": "No chargeback filed - cannot respond"
        }
    
    # Check if already resolved
    if transaction.chargeback_resolved_at:
        return {
            "status": "error",
            "message": "Chargeback already resolved - cannot add more responses"
        }
    
    # Update response notes and photos
    transaction.chargeback_evidence_notes = response_data.response_notes
    if response_data.evidence_photos:
        transaction.chargeback_evidence_photos = response_data.evidence_photos
    
    db.commit()
    
    print(f"✅ Chargeback response added for order {order_id}")
    print(f"   Response: {response_data.response_notes[:100]}...")
    
    return {
        "status": "success",
        "message": "Response submitted. Bank has been notified."
    }