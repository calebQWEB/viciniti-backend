from sqlalchemy.orm import Session
from app.models.notification import Notification
from app.services.email_service import send_notification_email
from app.models.user import User
from uuid import UUID

def create_notification(db: Session, user_id: UUID, message: str):
    notification = Notification(
        user_id=UUID(str(user_id)),
        message=message,
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)

    # Fetch user and send email
    user = db.query(User).filter(User.id == UUID(str(user_id))).first()
    if user:
        send_notification_email(
            to=user.email,
            name=user.name,
            notification_message=message
        )

    return notification

def get_notifications(db: Session, user_id: UUID):
    return db.query(Notification).filter(
        Notification.user_id == UUID(str(user_id))
    ).order_by(Notification.created_at.desc()).all()

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