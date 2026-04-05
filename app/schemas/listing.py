from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from app.models.listing import ListingStatus

# Represents a single image object stored in Cloudinary
class ImageObject(BaseModel):
    url: str
    public_id: str

class ListingBase(BaseModel):
    title: str
    description: str
    price: float
    category: str
    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

class ListingCreate(ListingBase):
    images: Optional[List[ImageObject]] = []

class ListingUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    category: Optional[str] = None
    images: Optional[List[ImageObject]] = None
    status: Optional[ListingStatus] = None
    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

class ListingResponse(ListingBase):
    id: UUID
    user_id: UUID
    images: List[ImageObject]
    status: ListingStatus
    created_at: datetime

    class Config:
        from_attributes = True