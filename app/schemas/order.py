from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from app.models.order import OrderStatus
from app.schemas.listing import ImageObject
from app.schemas.user import UserSummary

class ListingSummary(BaseModel):
    id: UUID
    title: str
    images: List[ImageObject]

    class Config:
        from_attributes = True

class ServiceSummary(BaseModel):
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

class OrderResponse(BaseModel):
    id: UUID
    listing_id: Optional[UUID] = None
    service_id: Optional[UUID] = None
    buyer_id: UUID
    seller_id: UUID
    amount: float
    fee: float
    status: OrderStatus
    created_at: datetime
    completed_at: Optional[datetime] = None
    completion_photos: Optional[list] = None
    completion_notes: Optional[str] = None
    buyer_accepted_at: Optional[datetime] = None
    payout_due_at: Optional[datetime] = None
    payout_completed_at: Optional[datetime] = None
    listing: Optional[ListingSummary] = None
    service: Optional[ServiceSummary] = None
    buyer: Optional[UserSummary] = None
    seller: Optional[UserSummary] = None

    class Config:
        from_attributes = True