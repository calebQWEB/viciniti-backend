from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from app.models.category import CategoryType

class CategoryResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    type: CategoryType
    icon: Optional[str] = None
    sort_order: int

    class Config:
        from_attributes = True