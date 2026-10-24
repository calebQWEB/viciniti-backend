from pydantic import BaseModel, Field, field_serializer
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from app.models.service import ServiceStatus
from app.utils.geo import blur_coordinate
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
    # Set when an admin removed it; only the seller ever sees these (removed items are hidden from everyone else)
    removed_at: Optional[datetime] = None
    removal_reason: Optional[str] = None
    owner: Optional[UserSummary] = None
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