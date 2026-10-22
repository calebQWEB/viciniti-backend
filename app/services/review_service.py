from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException, status
from uuid import UUID
from app.config import BRAND_NAME
from app.models.order import Order
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


def short_name(full_name: str) -> str:
    """'Tunde Adeyemi' -> 'Tunde A.'; single names are left as they are."""
    parts = (full_name or "").split()
    if not parts:
        return f"A {BRAND_NAME} user"
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]} {parts[-1][0].upper()}."


def get_seller_reviews(db: Session, seller_id: UUID) -> list:
    """Reviews for a seller's public profile, with who left them and what they were about."""
    reviews = (
        db.query(Review)
        .options(
            joinedload(Review.buyer),
            joinedload(Review.order).joinedload(Order.listing),
            joinedload(Review.order).joinedload(Order.service),
        )
        .filter(Review.seller_id == seller_id)
        .order_by(Review.created_at.desc())
        .all()
    )

    results = []
    for review in reviews:
        order = review.order
        is_service = order is not None and order.service_id is not None
        subject = (order.service if is_service else order.listing) if order else None
        results.append({
            "id": review.id,
            "rating": review.rating,
            "review_text": review.review_text,
            "created_at": review.created_at,
            "reviewer_name": short_name(review.buyer.name if review.buyer else ""),
            "kind": "booked" if is_service else "bought",
            # The listing or service may have been deleted since
            "subject_title": subject.title if subject else ("a service" if is_service else "an item"),
        })
    return results