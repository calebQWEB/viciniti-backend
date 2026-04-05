from pydantic import BaseModel
from datetime import datetime
from uuid import UUID

class NotificationResponse(BaseModel):
    id: UUID
    user_id: UUID
    message: str
    read: bool
    created_at: datetime

    class Config:
        from_attributes = True