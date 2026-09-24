from sqlalchemy.orm import Session
from app.models.notification import Notification, NotificationType
from app.services.email_service import send_notification_email
from app.models.user import User
from uuid import UUID
from typing import Optional
from math import ceil

def create_notification(
        db: Session,
        user_id: UUID,
        message: str,
        type: Optional[NotificationType] = None,
        link: Optional[str] = None,
):
    notification = Notification(
        user_id=UUID(str(user_id)),
        message=message,
        type=type,
        link=link,
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)

    user = db.query(User).filter(User.id == UUID(str(user_id))).first()
    if user:
        send_notification_email(
            to=user.email,
            name=user.name,
            notification_message=message
        )

    return notification

def get_notifications(
        db: Session,
        user_id: UUID,
        page: int = 1,
        limit: int = 20,
        unread_only: bool = False,
):
    query = db.query(Notification).filter(Notification.user_id == UUID(str(user_id)))

    if unread_only:
        query = query.filter(Notification.read == False)

    total = query.count()

    items = (
        query.order_by(Notification.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )

    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": max(1, ceil(total / limit)) if total else 1,
    }

def mark_as_read(db: Session, notification_id: UUID, user_id: UUID):
    notification = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.user_id == UUID(str(user_id))
    ).first()
    if notification:
        notification.read = True
        db.commit()
        db.refresh(notification)
    return notification

def mark_all_as_read(db: Session, user_id: UUID):
    db.query(Notification).filter(
        Notification.user_id == UUID(str(user_id)),
        Notification.read == False
    ).update({"read": True})
    db.commit()
    return {"message": "All notifications marked as read"}

def get_unread_count(db: Session, user_id: UUID):
    count = db.query(Notification).filter(
        Notification.user_id == UUID(str(user_id)),
        Notification.read == False
    ).count()
    return {"unread_count": count}