from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from typing import Optional

class ReviewCreate(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    review_text: Optional[str] = None

class ReviewResponse(BaseModel):
    id: UUID
    order_id: UUID
    buyer_id: UUID
    seller_id: UUID
    rating: int
    review_text: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True