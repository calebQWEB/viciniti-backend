# app/routers/home.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.listing import ListingResponse
from app.schemas.service import ServiceResponse
from app.services.home_service import get_featured_items, get_featured_services, get_platform_stats
from typing import List, Optional
from pydantic import BaseModel

router = APIRouter(prefix="/home", tags=["Home"])

class FeaturedResponse(BaseModel):
    items: List[ListingResponse]
    services: List[ServiceResponse]

class PlatformStats(BaseModel):
    active_listings: int
    total_users: int

@router.get("/featured", response_model=FeaturedResponse)
def featured(
        limit: int = Query(6, ge=1, le=12),
        latitude: Optional[float] = Query(None, ge=-90, le=90),
        longitude: Optional[float] = Query(None, ge=-180, le=180),
        radius_km: float = Query(50, gt=0, le=500),
        db: Session = Depends(get_db)
):
    location = {"latitude": latitude, "longitude": longitude, "radius_km": radius_km}
    return {
        "items": get_featured_items(db, limit=limit, **location),
        "services": get_featured_services(db, limit=limit, **location),
    }

@router.get("/stats", response_model=PlatformStats)
def stats(db: Session = Depends(get_db)):
    return get_platform_stats(db)