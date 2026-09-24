from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException, status
from app.models.message import Message
from app.models.notification import NotificationType
from app.schemas.message import MessageCreate
from app.services.notification_service import create_notification
from app.services.email_service import send_new_message_email
from app.models.user import User
from sqlalchemy import or_, and_, func
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
        f"You have a new message from {sender.name if sender else 'someone'}!",
        type=NotificationType.message,
        link=f"/dashboard/messages?contact={sender_id}",
    )

    return new_message

def get_conversation(db: Session, user_id: UUID, other_user_id: UUID):
    messages = (
        db.query(Message)
        .options(joinedload(Message.sender), joinedload(Message.receiver))
        .filter(
            (
                (Message.sender_id == UUID(str(user_id))) &
                (Message.receiver_id == UUID(str(other_user_id)))
            ) | (
                (Message.sender_id == UUID(str(other_user_id))) &
                (Message.receiver_id == UUID(str(user_id)))
            )
        )
        .order_by(Message.created_at.asc())
        .all()
    )

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

def get_contacts(db: Session, user_id: UUID):
    uid = UUID(str(user_id))

    # All messages involving this user, most recent first
    messages = (
        db.query(Message)
        .options(joinedload(Message.sender), joinedload(Message.receiver))
        .filter(or_(Message.sender_id == uid, Message.receiver_id == uid))
        .order_by(Message.created_at.desc())
        .all()
    )

    contacts = {}
    for msg in messages:
        other = msg.receiver if msg.sender_id == uid else msg.sender
        if other.id not in contacts:
            contacts[other.id] = {
                "user_id": other.id,
                "name": other.name,
                "avatar": other.avatar,
                "last_message": msg.content,
                "last_message_time": msg.created_at,
                "unread_count": 0,
            }
        if msg.receiver_id == uid and not msg.read:
            contacts[other.id]["unread_count"] += 1

    return list(contacts.values())