from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from uuid import UUID
from app.models.notification import NotificationType

class NotificationResponse(BaseModel):
    id: UUID
    user_id: UUID
    message: str
    type: Optional[NotificationType] = None
    link: Optional[str] = None
    read: bool
    created_at: datetime

    class Config:
        from_attributes = True