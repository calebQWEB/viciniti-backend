from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from uuid import UUID

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

    class Config:
        from_attributes = True
