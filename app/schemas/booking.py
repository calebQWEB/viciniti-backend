from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from app.models.booking import BookingStatus
from app.models.order import OrderStatus
from app.schemas.listing import ImageObject
from app.schemas.user import UserSummary

class ServiceSummary(BaseModel):
    id: UUID
    title: str
    images: List[ImageObject]

    class Config:
        from_attributes = True

class BookingBase(BaseModel):
    service_id: UUID
    scheduled_at: datetime

class BookingCreate(BookingBase):
    pass

class BookingUpdate(BaseModel):
    status: Optional[BookingStatus] = None
    scheduled_at: Optional[datetime] = None

class BookingResponse(BookingBase):
    id: UUID
    client_id: UUID
    provider_id: UUID
    order_id: Optional[UUID] = None
    order_status: Optional[OrderStatus] = None
    amount: float
    fee: float
    status: BookingStatus
    created_at: datetime
    service: Optional[ServiceSummary] = None
    client: Optional[UserSummary] = None
    provider: Optional[UserSummary] = None

    class Config:
        from_attributes = True