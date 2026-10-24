from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.services.suspension import publicly_visible
from app.models.listing import Listing, ListingStatus
from app.schemas.listing import ListingCreate, ListingUpdate
from app.utils.geo import distance_km, within_radius, attach_distances
from app.services.log_service import log_event
from uuid import UUID
import math

def create_listing(db: Session, listing_data: ListingCreate, user_id: UUID):
    # No payout account needed to list; payouts wait until one is added (see get_payout_blocked)
    from app.models.category import Category, CategoryType

    category = db.query(Category).filter(
        Category.id == listing_data.category_id,
        Category.type == CategoryType.item,
        Category.is_active == True
    ).first()
    if not category:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid category for a listing."
        )

    new_listing = Listing(
        user_id=UUID(str(user_id)),
        title=listing_data.title,
        description=listing_data.description,
        price=listing_data.price,
        category_id=listing_data.category_id,
        images=[img.model_dump() for img in listing_data.images or []],
        location=listing_data.location,
        latitude=listing_data.latitude,
        longitude=listing_data.longitude,
    )
    db.add(new_listing)
    db.commit()
    db.refresh(new_listing)
    log_event("info", "listing", "listing.created", "Listing created",
              details={"listing_id": new_listing.id, "price": new_listing.price}, user_id=user_id)
    return new_listing

def get_listings(db: Session, category: str = None, location: str = None,
                 latitude: float = None, longitude: float = None,
                 radius_km: float = 50, sort: str = None, q: str = None,
                 skip: int = 0, limit: int = 20):
    from app.models.category import Category
    from sqlalchemy.orm import joinedload

    query = (
        db.query(Listing)
        .options(joinedload(Listing.category_ref))
        .filter(Listing.status == ListingStatus.active, publicly_visible(Listing))
    )

    if category:
        query = query.join(Category, Listing.category_id == Category.id).filter(Category.slug == category)
    if location:
        query = query.filter(Listing.location.ilike(f"%{location}%"))
    if q and q.strip():
        term = q.strip()
        query = query.filter(or_(
            Listing.title.icontains(term, autoescape=True),
            Listing.description.icontains(term, autoescape=True),
        ))

    if latitude is None or longitude is None:
        return query.order_by(Listing.created_at.desc()).offset(skip).limit(limit).all()

    # Radius filter runs in SQL before paging, so every page is full
    distance = distance_km(Listing.latitude, Listing.longitude, latitude, longitude)
    query = (
        query.filter(*within_radius(Listing.latitude, Listing.longitude, latitude, longitude, radius_km))
        .add_columns(distance)
    )
    if sort == "newest":
        query = query.order_by(Listing.created_at.desc())
    else:
        query = query.order_by(distance, Listing.created_at.desc())

    return attach_distances(query.offset(skip).limit(limit).all())

def get_user_listings(
    db: Session,
    user_id: UUID,
    page: int = 1,
    limit: int = 20,
    status_filter: Optional[str] = None,
):
    query = db.query(Listing).filter(Listing.user_id == user_id)

    if status_filter and status_filter != "all":
        try:
            status_enum = ListingStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status filter: {status_filter}"
            )
        query = query.filter(Listing.status == status_enum)

    total = query.count()

    items = (
        query.order_by(Listing.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )

    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": max(1, math.ceil(total / limit)) if total else 1,
    }

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

def get_listing_status_counts(db: Session, user_id: UUID):
    rows = (
        db.query(Listing.status, func.count(Listing.id))
        .filter(Listing.user_id == user_id)
        .group_by(Listing.status)
        .all()
    )
    counts = {s.value: 0 for s in ListingStatus}
    for status_val, count in rows:
        counts[status_val.value] = count
    counts["all"] = sum(counts.values())
    return counts

def update_listing(db: Session, listing_id: UUID, listing_data: ListingUpdate, user_id: UUID):
    listing = get_listing(db, listing_id)

    if listing.user_id != UUID(str(user_id)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to update this listing"
        )
    if listing.removed_at:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This listing was removed by Junction and can't be edited."
        )

    update_data = listing_data.model_dump(exclude_unset=True)

    # Keeping a retired category is fine; only a change has to pick an active one
    if "category_id" in update_data and update_data["category_id"] != listing.category_id:
        from app.models.category import Category, CategoryType
        category = db.query(Category).filter(
            Category.id == update_data["category_id"],
            Category.type == CategoryType.item,
            Category.is_active == True
        ).first()
        if not category:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid category for a listing."
            )

    for field, value in update_data.items():
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
    log_event("info", "listing", "listing.deleted", "Listing deleted",
              details={"listing_id": listing_id}, user_id=user_id)
    return {"message": "Listing deleted successfully"}