from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models.service import Service, ServiceStatus
from app.schemas.service import ServiceCreate, ServiceUpdate
from uuid import UUID
import math

def create_service(db: Session, service_data: ServiceCreate, user_id: UUID):
    new_service = Service(
        user_id=UUID(str(user_id)),
        title=service_data.title,
        description=service_data.description,
        price=service_data.price,
        category=service_data.category,
        images=[img.model_dump() for img in service_data.images or []],
        location=service_data.location,
        latitude=service_data.latitude,
        longitude=service_data.longitude,
    )
    db.add(new_service)
    db.commit()
    db.refresh(new_service)
    return new_service

def get_services(db: Session, category: str = None, location: str = None,
                 latitude: float = None, longitude: float = None,
                 radius_km: float = 50, skip: int = 0, limit: int = 20):
    query = (
        db.query(Service)
        .filter(Service.status == ServiceStatus.active)
        .order_by(Service.created_at.desc())
    )

    if category:
        query = query.filter(Service.category == category)
    if location:
        query = query.filter(Service.location.ilike(f"%{location}%"))

    services = query.offset(skip).limit(limit).all()

    if latitude and longitude:
        services = [
            service for service in services
            if service.latitude and service.longitude and
            _calculate_distance(latitude, longitude, service.latitude, service.longitude) <= radius_km
        ]

    return services

def get_user_services(db: Session, user_id: UUID):
    return (
        db.query(Service)
        .filter(Service.user_id == user_id)
        .order_by(Service.created_at.desc())
        .all()
    )

def get_service(db: Session, service_id: UUID):
    service = (
        db.query(Service)
        .filter(Service.id == service_id)
        .first()
    )
    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found"
        )
    return service

def update_service(db: Session, service_id: UUID, service_data: ServiceUpdate, user_id: UUID):
    service = get_service(db, service_id)

    if service.user_id != UUID(str(user_id)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to update this service"
        )

    for field, value in service_data.model_dump(exclude_unset=True).items():
        setattr(service, field, value)

    db.commit()
    db.refresh(service)
    return service

def delete_service(db: Session, service_id: UUID, user_id: UUID):
    service = get_service(db, service_id)

    if service.user_id != UUID(str(user_id)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to delete this service"
        )

    db.delete(service)
    db.commit()
    return {"message": "Service deleted successfully"}

def _calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c