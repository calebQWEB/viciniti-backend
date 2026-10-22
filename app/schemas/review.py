from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from typing import Literal, Optional

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
# What anyone can see about a review on a seller's profile: no user or order IDs
class PublicReviewResponse(BaseModel):
    id: UUID
    rating: int
    review_text: Optional[str] = None
    created_at: datetime
    # First name and last initial, e.g. "Tunde A."
    reviewer_name: str
    kind: Literal["bought", "booked"]
    # The listing or service the review is about
    subject_title: str
