from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from app.models.service import ServiceStatus
from app.schemas.listing import ImageObject

class ServiceBase(BaseModel):
    title: str
    description: str
    price: float
    category: str
    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

class ServiceCreate(ServiceBase):
    images: Optional[List[ImageObject]] = []

class ServiceUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    category: Optional[str] = None
    images: Optional[List[ImageObject]] = None
    status: Optional[ServiceStatus] = None
    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

class ServiceResponse(ServiceBase):
    id: UUID
    user_id: UUID
    images: List[ImageObject]
    status: ServiceStatus
    created_at: datetime

    class Config:
        from_attributes = True