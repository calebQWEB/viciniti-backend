# app/services/home_service.py
from sqlalchemy.orm import Session, joinedload
from app.models.listing import Listing, ListingStatus
from app.models.service import Service, ServiceStatus
from app.utils.geo import distance_km, within_radius, attach_distances

def _get_featured(db: Session, model, active_status, limit: int,
                  latitude: float = None, longitude: float = None, radius_km: float = 50):
    """Active rows capped at one per seller: nearest first when a location is given, else most recent.
    With a location, only rows inside the radius are returned (possibly none)."""
    query = (
        db.query(model)
        .options(joinedload(model.owner))
        .filter(model.status == active_status)
    )

    if latitude is None or longitude is None:
        query = query.order_by(model.created_at.desc())
    else:
        distance = distance_km(model.latitude, model.longitude, latitude, longitude)
        query = (
            query.filter(*within_radius(model.latitude, model.longitude, latitude, longitude, radius_km))
            .add_columns(distance)
            .order_by(distance, model.created_at.desc())
        )

    candidates = query.limit(limit * 4).all()  # over-fetch to leave room for per-seller de-duplication
    if latitude is not None and longitude is not None:
        candidates = attach_distances(candidates)

    seen_sellers = set()
    result = []
    for row in candidates:
        if row.user_id in seen_sellers:
            continue
        seen_sellers.add(row.user_id)
        result.append(row)
        if len(result) >= limit:
            break
    return result

def get_featured_items(db: Session, limit: int = 6, **location):
    return _get_featured(db, Listing, ListingStatus.active, limit, **location)

def get_featured_services(db: Session, limit: int = 6, **location):
    return _get_featured(db, Service, ServiceStatus.active, limit, **location)

def get_platform_stats(db: Session):
    active_listings = db.query(Listing).filter(Listing.status == ListingStatus.active).count()
    active_services = db.query(Service).filter(Service.status == ServiceStatus.active).count()
    from app.models.user import User
    total_users = db.query(User).count()
    return {
        "active_listings": active_listings + active_services,
        "total_users": total_users,
    }