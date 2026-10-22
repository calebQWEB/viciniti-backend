from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.listing import ListingCreate, ListingUpdate, ListingResponse
from app.services.listing_service import (
    create_listing, get_listing_status_counts, get_listings, get_listing,
    get_user_listings, update_listing, delete_listing
)
from app.utils.security import get_current_user, get_optional_user
from app.utils.geo import mark_owner_view
from typing import List, Literal, Optional
from uuid import UUID

router = APIRouter(prefix="/listings", tags=["Listings"])

# Create a new listing
@router.post("/", response_model=ListingResponse)
def create(
    listing_data: ListingCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return mark_owner_view(create_listing(db, listing_data, current_user["sub"]))

# Browse all listings with optional filters
@router.get("/", response_model=List[ListingResponse])
def browse(
    category: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    # Free-text search over title and description
    q: Optional[str] = Query(None, max_length=100),
    latitude: Optional[float] = Query(None, ge=-90, le=90),
    longitude: Optional[float] = Query(None, ge=-180, le=180),
    radius_km: float = Query(50, gt=0, le=500),
    # Defaults to nearest when a location is given, otherwise newest
    sort: Optional[Literal["nearest", "newest"]] = Query(None),
    skip: int = Query(0),
    limit: int = Query(20),
    db: Session = Depends(get_db)
):
    return get_listings(
        db, category=category, location=location,
        latitude=latitude, longitude=longitude, radius_km=radius_km,
        sort=sort, q=q, skip=skip, limit=limit,
    )

# Get current user's listings
@router.get("/me")
def my_listings(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    status: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return get_user_listings(
        db, current_user["sub"], page=page, limit=limit, status_filter=status
    )

@router.get("/me/counts")
def my_listings_counts(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return get_listing_status_counts(db, current_user["sub"])

# Get a single listing by ID
@router.get("/{listing_id}", response_model=ListingResponse)
def get_one(
    listing_id: UUID,
    current_user: Optional[dict] = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    listing = get_listing(db, listing_id)
    # Owners (e.g. the edit page) get exact coordinates; everyone else gets blurred ones
    if current_user and str(listing.user_id) == current_user.get("sub"):
        mark_owner_view(listing)
    return listing

# Update a listing
@router.put("/{listing_id}", response_model=ListingResponse)
def update(
    listing_id: UUID,
    listing_data: ListingUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return mark_owner_view(update_listing(db, listing_id, listing_data, current_user["sub"]))

# Delete a listing
@router.delete("/{listing_id}")
def delete(
    listing_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return delete_listing(db, listing_id, current_user["sub"])