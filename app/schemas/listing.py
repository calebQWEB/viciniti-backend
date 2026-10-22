from pydantic import BaseModel, Field, field_serializer
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from app.models.listing import ListingStatus
from app.utils.geo import blur_coordinate

# Represents a single image object stored in Cloudinary
class ImageObject(BaseModel):
    url: str
    public_id: str

class ListingBase(BaseModel):
    title: str
    description: str
    price: float
    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

class ListingCreate(ListingBase):
    category_id: UUID
    images: Optional[List[ImageObject]] = []

class ListingUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    category_id: Optional[UUID] = None
    images: Optional[List[ImageObject]] = None
    status: Optional[ListingStatus] = None
    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

class CategorySummary(BaseModel):
    id: UUID
    name: str
    slug: str

    class Config:
        from_attributes = True

class ListingResponse(ListingBase):
    id: UUID
    user_id: UUID
    category_id: Optional[UUID] = None
    images: List[ImageObject]
    status: ListingStatus
    created_at: datetime
    category: Optional[CategorySummary] = Field(None, alias="category_ref")
    # Only set when the request included a location
    distance_km: Optional[float] = None
    # Set (via mark_owner_view) only on the owner's own requests; never sent to clients
    exact_coordinates: bool = Field(False, exclude=True)

    @field_serializer("latitude", "longitude")
    def _blur_for_public(self, value: Optional[float]) -> Optional[float]:
        return value if self.exact_coordinates else blur_coordinate(value)

    class Config:
        from_attributes = True