from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models.listing import Listing, ListingStatus
from app.schemas.listing import ListingCreate, ListingUpdate
from uuid import UUID
import math

def create_listing(db: Session, listing_data: ListingCreate, user_id: UUID):
    new_listing = Listing(
        user_id=UUID(str(user_id)),
        title=listing_data.title,
        description=listing_data.description,
        price=listing_data.price,
        category=listing_data.category,
        images=[img.model_dump() for img in listing_data.images or []],
        location=listing_data.location,
        latitude=listing_data.latitude,
        longitude=listing_data.longitude,
    )
    db.add(new_listing)
    db.commit()
    db.refresh(new_listing)
    return new_listing

def get_listings(db: Session, category: str = None, location: str = None,
                 latitude: float = None, longitude: float = None,
                 radius_km: float = 50, skip: int = 0, limit: int = 20):
    query = (
        db.query(Listing)
        .filter(Listing.status == ListingStatus.active)
        .order_by(Listing.created_at.desc())
    )

    if category:
        query = query.filter(Listing.category == category)
    if location:
        query = query.filter(Listing.location.ilike(f"%{location}%"))

    listings = query.offset(skip).limit(limit).all()

    if latitude and longitude:
        listings = [
            listing for listing in listings
            if listing.latitude and listing.longitude and
            _calculate_distance(latitude, longitude, listing.latitude, listing.longitude) <= radius_km
        ]

    return listings

def get_user_listings(db: Session, user_id: UUID):
    return (
        db.query(Listing)
        .filter(Listing.user_id == user_id)
        .order_by(Listing.created_at.desc())
        .all()
    )

def get_listing(db: Session, listing_id: UUID):
    listing = (
        db.query(Listing)
        .filter(Listing.id == listing_id)
        .first()
    )
    if not listing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Listing not found"
        )
    return listing

def update_listing(db: Session, listing_id: UUID, listing_data: ListingUpdate, user_id: UUID):
    listing = get_listing(db, listing_id)

    # Make sure the listing belongs to the current user
    if listing.user_id != UUID(str(user_id)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to update this listing"
        )

    for field, value in listing_data.model_dump(exclude_unset=True).items():
        setattr(listing, field, value)

    db.commit()
    db.refresh(listing)
    return listing

def delete_listing(db: Session, listing_id: UUID, user_id: UUID):
    listing = get_listing(db, listing_id)

    # Make sure the listing belongs to the current user
    if listing.user_id != UUID(str(user_id)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to delete this listing"
        )

    db.delete(listing)
    db.commit()
    return {"message": "Listing deleted successfully"}

def _calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    # Haversine formula - calculates distance between two coordinates in km
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c