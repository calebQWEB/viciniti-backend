from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.notification import NotificationResponse
from app.services.notification_service import (
    get_notifications, mark_as_read,
    mark_all_as_read, get_unread_count
)
from app.utils.security import get_current_user
from typing import List
from uuid import UUID

router = APIRouter(prefix="/notifications", tags=["Notifications"])

# Get all notifications for current user
@router.get("/", response_model=List[NotificationResponse])
def get_all(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return get_notifications(db, current_user["sub"])

# Get unread notification count
@router.get("/unread-count")
def unread_count(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return get_unread_count(db, current_user["sub"])

# Mark all notifications as read ← moved above /{notification_id}
@router.put("/mark-all-read")
def read_all(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return mark_all_as_read(db, current_user["sub"])

# Mark a single notification as read ← now below /mark-all-read
@router.put("/{notification_id}")
def read_one(
    notification_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return mark_as_read(db, notification_id, current_user["sub"])