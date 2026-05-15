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
        current_user["sub"],
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
        current_user["sub"],
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