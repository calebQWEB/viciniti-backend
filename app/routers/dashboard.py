# app/routers/dashboard.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.services.dashboard_service import get_action_items, get_dashboard_stats, get_recent_activity, get_badge_counts, get_getting_started
from app.utils.security import get_current_user
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from app.services.dashboard_service import get_recent_activity
from app.models.notification import NotificationType
from uuid import UUID

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


class DashboardStats(BaseModel):
    balance: float
    active_listings: int
    pending_orders: int
    unread_messages: int

class BadgeCounts(BaseModel):
    purchases: int
    bookings: int
    messages: int
    notifications: int
    profile: int

class ActionItem(BaseModel):
    type: str
    title: str
    subtitle: Optional[str] = None
    link: str
    count: Optional[int] = None
    created_at: datetime

class GettingStarted(BaseModel):
    has_location: bool
    has_avatar: bool
    has_payout_account: bool
    has_listing_or_service: bool

class RecentActivityItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    message: str
    type: Optional[NotificationType] = None
    link: Optional[str] = None
    read: bool
    created_at: datetime

@router.get("/stats", response_model=DashboardStats)
def dashboard_stats(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_dashboard_stats(db, current_user["sub"])

@router.get("/action-items", response_model=List[ActionItem])
def action_items(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return get_action_items(db, current_user["sub"])

@router.get("/recent-activity", response_model=List[RecentActivityItem])
def recent_activity(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return get_recent_activity(db, current_user["sub"])


@router.get("/badge-counts", response_model=BadgeCounts)
def badge_counts(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return get_badge_counts(db, current_user["sub"])

@router.get("/getting-started", response_model=GettingStarted)
def getting_started(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return get_getting_started(db, current_user["sub"])
