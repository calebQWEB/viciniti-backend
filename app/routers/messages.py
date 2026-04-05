from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.message import MessageCreate, MessageResponse
from app.services.message_service import (
    send_message, get_conversation, get_inbox, get_unread_count
)
from app.utils.security import get_current_user
from typing import List
from uuid import UUID

router = APIRouter(prefix="/messages", tags=["Messages"])

# Send a message
@router.post("/", response_model=MessageResponse)
def send(
    message_data: MessageCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return send_message(db, message_data, current_user["sub"])

# Get conversation between two users
@router.get("/conversation/{other_user_id}", response_model=List[MessageResponse])
def conversation(
    other_user_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return get_conversation(db, current_user["sub"], other_user_id)

# Get inbox
@router.get("/inbox", response_model=List[MessageResponse])
def inbox(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return get_inbox(db, current_user["sub"])

# Get unread message count
@router.get("/unread-count")
def unread_count(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return get_unread_count(db, current_user["sub"])
