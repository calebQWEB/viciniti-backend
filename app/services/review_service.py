from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from uuid import UUID
from app.models.review import Review
from app.schemas.review import ReviewCreate

def create_review(db: Session, order_id: UUID, buyer_id: UUID, seller_id: UUID, data: ReviewCreate) -> Review:
    # Check if review already exists for this order
    existing_review = db.query(Review).filter(Review.order_id == order_id).first()
    if existing_review:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A review already exists for this order"
        )

    review = Review(
        order_id=order_id,
        buyer_id=buyer_id,
        seller_id=seller_id,
        rating=data.rating,
        review_text=data.review_text,
    )

    db.add(review)
    db.commit()
    db.refresh(review)
    return review


def get_seller_reviews(db: Session, seller_id: UUID):
    return db.query(Review).filter(Review.seller_id == seller_id).order_by(Review.created_at.desc()).all()