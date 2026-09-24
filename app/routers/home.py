# app/routers/home.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.listing import ListingResponse
from app.schemas.service import ServiceResponse
from app.services.home_service import get_featured_items, get_featured_services, get_platform_stats
from typing import List
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
        db: Session = Depends(get_db)
):
    return {
        "items": get_featured_items(db, limit=limit),
        "services": get_featured_services(db, limit=limit),
    }

@router.get("/stats", response_model=PlatformStats)
def stats(db: Session = Depends(get_db)):
    return get_platform_stats(db)