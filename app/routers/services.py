from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.service import ServiceCreate, ServiceUpdate, ServiceResponse
from app.services.service_service import (
    create_service, get_services, get_service,
    get_user_services, update_service, delete_service
)
from app.utils.security import get_current_user
from typing import List, Optional
from uuid import UUID

router = APIRouter(prefix="/services", tags=["Services"])

# Create a new service
@router.post("/", response_model=ServiceResponse)
def create(
    service_data: ServiceCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return create_service(db, service_data, current_user["sub"])

# Browse all services with optional filters
@router.get("/", response_model=List[ServiceResponse])
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
    return get_services(db, category, location, latitude, longitude, radius_km, skip, limit)

# Get current user's services
@router.get("/me", response_model=List[ServiceResponse])
def my_services(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return get_user_services(db, current_user["sub"])

# Get a single service by ID
@router.get("/{service_id}", response_model=ServiceResponse)
def get_one(service_id: UUID, db: Session = Depends(get_db)):
    return get_service(db, service_id)

# Update a service
@router.put("/{service_id}", response_model=ServiceResponse)
def update(
    service_id: UUID,
    service_data: ServiceUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return update_service(db, service_id, service_data, current_user["sub"])

# Delete a service
@router.delete("/{service_id}")
def delete(
    service_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return delete_service(db, service_id, current_user["sub"])