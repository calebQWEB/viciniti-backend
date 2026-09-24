from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from app.models.service import ServiceStatus
from app.schemas.listing import ImageObject
from app.schemas.user import UserSummary

class ServiceBase(BaseModel):
    title: str
    description: str
    price: float
    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

class ServiceCreate(ServiceBase):
    category_id: UUID
    images: Optional[List[ImageObject]] = []

class ServiceUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    category_id: Optional[UUID] = None
    images: Optional[List[ImageObject]] = None
    status: Optional[ServiceStatus] = None
    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

class CategorySummary(BaseModel):
    id: UUID
    name: str
    slug: str

    class Config:
        from_attributes = True

class ServiceResponse(ServiceBase):
    id: UUID
    user_id: UUID
    category_id: Optional[UUID] = None
    images: List[ImageObject]
    status: ServiceStatus
    created_at: datetime
    owner: Optional[UserSummary] = None
    category: Optional[CategorySummary] = Field(None, alias="category_ref")

    class Config:
        from_attributes = True