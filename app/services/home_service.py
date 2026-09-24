# app/services/home_service.py
from sqlalchemy.orm import Session, joinedload
from app.models.listing import Listing, ListingStatus
from app.models.service import Service, ServiceStatus

def get_featured_items(db: Session, limit: int = 6):
    """Most recent active listings, capped at one per seller."""
    candidates = (
        db.query(Listing)
        .options(joinedload(Listing.owner))
        .filter(Listing.status == ListingStatus.active)
        .order_by(Listing.created_at.desc())
        .limit(limit * 4)  # over-fetch to leave room for per-seller de-duplication
        .all()
    )
    seen_sellers = set()
    result = []
    for listing in candidates:
        if listing.user_id in seen_sellers:
            continue
        seen_sellers.add(listing.user_id)
        result.append(listing)
        if len(result) >= limit:
            break
    return result

def get_featured_services(db: Session, limit: int = 6):
    """Most recent active services, capped at one per seller."""
    candidates = (
        db.query(Service)
        .options(joinedload(Service.owner))
        .filter(Service.status == ServiceStatus.active)
        .order_by(Service.created_at.desc())
        .limit(limit * 4)
        .all()
    )
    seen_sellers = set()
    result = []
    for service in candidates:
        if service.user_id in seen_sellers:
            continue
        seen_sellers.add(service.user_id)
        result.append(service)
        if len(result) >= limit:
            break
    return result

def get_platform_stats(db: Session):
    active_listings = db.query(Listing).filter(Listing.status == ListingStatus.active).count()
    active_services = db.query(Service).filter(Service.status == ServiceStatus.active).count()
    from app.models.user import User
    total_users = db.query(User).count()
    return {
        "active_listings": active_listings + active_services,
        "total_users": total_users,
    }