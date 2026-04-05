from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas import OrderCreate, OrderUpdate, OrderResponse
from app.services.order_service import (
    create_order, get_buyer_orders, get_seller_orders, get_order, update_order
)
from app.utils.security import get_current_user
from typing import List
from uuid import UUID

router = APIRouter(prefix="/orders", tags=["orders"])

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