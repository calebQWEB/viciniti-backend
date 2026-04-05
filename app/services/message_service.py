from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models.message import Message
from app.schemas.message import MessageCreate
from app.services.notification_service import create_notification
from app.services.email_service import send_new_message_email
from app.models.user import User
from uuid import UUID

def send_message(db: Session, message_data: MessageCreate, sender_id: UUID):
    # Prevent messaging yourself
    if UUID(str(sender_id)) == message_data.receiver_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot send a message to yourself"
        )

    new_message = Message(
        sender_id=UUID(str(sender_id)),
        receiver_id=message_data.receiver_id,
        content=message_data.content,
    )

    db.add(new_message)
    db.commit()
    db.refresh(new_message)

    # Fetch sender and receiver details
    sender = db.query(User).filter(User.id == UUID(str(sender_id))).first()
    receiver = db.query(User).filter(User.id == message_data.receiver_id).first()

    # Send email to receiver
    if sender and receiver:
        send_new_message_email(
            to=receiver.email,
            name=receiver.name,
            sender_name=sender.name
        )

    # Notify receiver in-app
    create_notification(
        db,
        new_message.receiver_id,
        f"You have a new message from {sender.name if sender else 'someone'}!"
    )

    return new_message

def get_conversation(db: Session, user_id: UUID, other_user_id: UUID):
    # Get all messages between two users
    messages = db.query(Message).filter(
        (
            (Message.sender_id == UUID(str(user_id))) &
            (Message.receiver_id == UUID(str(other_user_id)))
        ) | (
            (Message.sender_id == UUID(str(other_user_id))) &
            (Message.receiver_id == UUID(str(user_id)))
        )
    ).order_by(Message.created_at.asc()).all()

    # Mark unread messages as read
    for message in messages:
        if message.receiver_id == UUID(str(user_id)) and not message.read:
            message.read = True

    db.commit()
    return messages

def get_inbox(db: Session, user_id: UUID):
    # Get all messages received by user
    return db.query(Message).filter(
        Message.receiver_id == UUID(str(user_id))
    ).order_by(Message.created_at.desc()).all()

def get_unread_count(db: Session, user_id: UUID):
    count = db.query(Message).filter(
        Message.receiver_id == UUID(str(user_id)),
        Message.read == False
    ).count()
    return {"unread_count": count}