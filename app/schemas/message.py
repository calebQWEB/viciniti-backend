from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from uuid import UUID
from app.schemas.user import UserSummary

class MessageBase(BaseModel):
    content: str

class MessageCreate(MessageBase):
    receiver_id: UUID

class MessageResponse(MessageBase):
    id: UUID
    sender_id: UUID
    receiver_id: UUID
    read: bool
    created_at: datetime
    sender: Optional[UserSummary] = None
    receiver: Optional[UserSummary] = None

    class Config:
        from_attributes = True

class ContactResponse(BaseModel):
    user_id: UUID
    name: str
    avatar: Optional[str] = None
    last_message: str
    last_message_time: datetime
    unread_count: int

    class Config:
        from_attributes = True