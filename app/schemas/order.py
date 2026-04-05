from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from app.models.order import OrderStatus
from app.schemas.listing import ImageObject

class ListingSummary(BaseModel):
    id: UUID
    title: str
    images: List[ImageObject]

    class Config:
        from_attributes = True

class OrderBase(BaseModel):
    listing_id: UUID

class OrderCreate(OrderBase):
    pass

class OrderUpdate(BaseModel):
    status: Optional[OrderStatus] = None

class OrderResponse(OrderBase):
    id: UUID
    buyer_id: UUID
    seller_id: UUID
    amount: float
    fee: float
    status: OrderStatus
    created_at: datetime
    listing: Optional[ListingSummary] = None

    class Config:
        from_attributes = True