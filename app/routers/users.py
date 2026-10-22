from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.models.order import Order, OrderStatus
from app.models.listing import Listing, ListingStatus
from app.models.service import Service, ServiceStatus
from app.models.transaction import Transaction, TransactionStatus
from app.schemas.user import UserResponse, PublicUserResponse, UserUpdate, PasswordChange
from app.schemas.listing import ListingResponse
from app.schemas.service import ServiceResponse
from app.schemas.review import PublicReviewResponse
from pydantic import BaseModel
from typing import List
from app.utils.security import get_current_user, verify_password, hash_password
from app.services.log_service import log_event
from uuid import UUID
from datetime import datetime

router = APIRouter(prefix="/users", tags=["Users"])

# Get current logged in user profile
@router.get("/me", response_model=UserResponse)
def get_me(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == current_user["sub"]).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return user

# Get any user's public profile by ID (no email or coordinates)
@router.get("/{user_id}", response_model=PublicUserResponse)
def get_user(user_id: UUID, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return user

# Update current logged in user profile
@router.put("/me", response_model=UserResponse)
def update_me(
    user_data: UserUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == current_user["sub"]).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Only update fields that were provided
    for field, value in user_data.model_dump(exclude_unset=True).items():
        setattr(user, field, value)

    db.commit()
    db.refresh(user)
    return user

# Password change
@router.put("/me/change-password")
def change_password(
    password_data: PasswordChange,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == current_user["sub"]).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Block Google OAuth users — they have no password
    if not user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This account uses Google sign-in. Password change is not available."
        )

    # Verify current password
    if not verify_password(password_data.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )

    # Enforce minimum password length
    if len(password_data.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 8 characters"
        )

    user.password_hash = hash_password(password_data.new_password)
    db.commit()
    log_event("info", "auth", "auth.password_changed", "Password changed", user_id=user.id)

    return {"message": "Password changed successfully"}

# Mark the welcome flow as finished (or skipped)
@router.post("/me/complete-onboarding", response_model=UserResponse)
def complete_onboarding(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == current_user["sub"]).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    if user.onboarded_at is None:
        user.onboarded_at = datetime.utcnow()
        db.commit()
        db.refresh(user)
        log_event("info", "auth", "user.onboarded", "Finished or skipped the welcome flow",
                  details={"intent": user.intent}, user_id=user.id)
    return user

class UserStatsResponse(BaseModel):
    # Public listing schemas, so coordinates are blurred like everywhere else
    listings: List[ListingResponse]
    services: List[ServiceResponse]
    completed_orders_count: int

@router.get("/{user_id}/stats", response_model=UserStatsResponse)
def get_user_stats(user_id: UUID, db: Session = Depends(get_db)):
    # Get active listings
    listings = db.query(Listing).filter(
        Listing.user_id == user_id,
        Listing.status == ListingStatus.active
    ).all()

    # Get active services
    services = db.query(Service).filter(
        Service.user_id == user_id,
        Service.status == ServiceStatus.active
    ).all()

    # Count completed orders as seller
    completed_orders_count = db.query(Order).filter(
        Order.seller_id == user_id,
        Order.status == OrderStatus.completed
    ).count()

    return {
        "listings": listings,
        "services": services,
        "completed_orders_count": completed_orders_count,
    }

# Public reviews for a seller: reviewer's short name and what was bought or booked, no IDs
@router.get("/{user_id}/reviews", response_model=List[PublicReviewResponse])
def get_reviews(
    user_id: UUID,
    db: Session = Depends(get_db)
):
    from app.services.review_service import get_seller_reviews
    return get_seller_reviews(db, user_id)