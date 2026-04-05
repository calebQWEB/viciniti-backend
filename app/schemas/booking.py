from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from app.models.booking import BookingStatus
from app.schemas.listing import ImageObject

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
    amount: float
    fee: float
    status: BookingStatus
    created_at: datetime
    service: Optional[ServiceSummary] = None

    class Config:
        from_attributes = True