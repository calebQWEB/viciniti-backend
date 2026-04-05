from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.listing import ListingCreate, ListingUpdate, ListingResponse
from app.services.listing_service import (
    create_listing, get_listings, get_listing,
    get_user_listings, update_listing, delete_listing
)
from app.utils.security import get_current_user
from typing import List, Optional
from uuid import UUID

router = APIRouter(prefix="/listings", tags=["Listings"])

# Create a new listing
@router.post("/", response_model=ListingResponse)
def create(
    listing_data: ListingCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return create_listing(db, listing_data, current_user["sub"])

# Browse all listings with optional filters
@router.get("/", response_model=List[ListingResponse])
def browse(
    category: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    latitude: Optional[float] = Query(None),
    longitude: Optional[float] = Query(None),
    radius_km: Optional[float] = Query(50),
    skip: int = Query(0),
    limit: int = Query(20),
    db: Session = Depends(get_db)
):
    return get_listings(db, category, location, latitude, longitude, radius_km, skip, limit)

# Get current user's listings
@router.get("/me", response_model=List[ListingResponse])
def my_listings(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return get_user_listings(db, current_user["sub"])

# Get a single listing by ID
@router.get("/{listing_id}", response_model=ListingResponse)
def get_one(listing_id: UUID, db: Session = Depends(get_db)):
    return get_listing(db, listing_id)

# Update a listing
@router.put("/{listing_id}", response_model=ListingResponse)
def update(
    listing_id: UUID,
    listing_data: ListingUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return update_listing(db, listing_id, listing_data, current_user["sub"])

# Delete a listing
@router.delete("/{listing_id}")
def delete(
    listing_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return delete_listing(db, listing_id, current_user["sub"])