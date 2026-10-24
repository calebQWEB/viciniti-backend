"""Queries and actions behind the admin Listings pages: browse everything, remove and restore."""
from datetime import datetime
from math import ceil
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.models.booking import Booking
from app.models.listing import Listing
from app.models.notification import NotificationType
from app.models.order import Order
from app.models.service import Service
from app.models.user import User
from app.services.email_service import send_listing_removed_email, send_listing_restored_email
from app.services.log_service import log_event
from app.services.notification_service import create_notification

MODELS = {"item": Listing, "service": Service}
# What the seller calls it, and where they manage it
WORDS = {"item": "listing", "service": "service"}
DASHBOARD_LINKS = {"item": "/dashboard/listings", "service": "/dashboard/services"}


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _person(user: Optional[User]) -> Optional[dict]:
    return {"id": user.id, "name": user.name, "email": user.email} if user else None


def _image_urls(row) -> list:
    return [image["url"] for image in (row.images or []) if isinstance(image, dict) and image.get("url")]


def _listing_item(kind: str, row) -> dict:
    urls = _image_urls(row)
    category = row.category_ref
    return {
        "id": row.id,
        "kind": kind,
        "title": row.title,
        "price": row.price,
        "status": row.status.value,
        "thumbnail": urls[0] if urls else None,
        "location": row.location,
        "category": {"id": category.id, "name": category.name, "slug": category.slug} if category else None,
        "seller": _person(row.owner) or {"id": UUID(int=0), "name": "Deleted user", "email": ""},
        "seller_suspended": bool(row.owner and row.owner.is_suspended),
        "created_at": row.created_at,
        "removed_at": row.removed_at,
        "removal_reason": row.removal_reason,
    }


def list_listings(db: Session, kind: str, page: int = 1, limit: int = 25, search: Optional[str] = None,
                  status_filter: Optional[str] = None, category_id: Optional[UUID] = None,
                  seller_id: Optional[UUID] = None) -> dict:
    model = MODELS[kind]
    query = db.query(model).join(User, model.user_id == User.id)

    if status_filter == "removed":
        query = query.filter(model.removed_at.isnot(None))
    elif status_filter:
        statuses = {s.value: s for s in model.status.type.enum_class}
        if status_filter not in statuses:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown status: {status_filter}")
        query = query.filter(model.status == statuses[status_filter], model.removed_at.is_(None))

    if category_id:
        query = query.filter(model.category_id == category_id)
    if seller_id:
        query = query.filter(model.user_id == seller_id)
    if search and search.strip():
        pattern = f"%{_escape_like(search.strip())}%"
        query = query.filter(or_(
            model.title.ilike(pattern, escape="\\"),
            User.name.ilike(pattern, escape="\\"),
            User.email.ilike(pattern, escape="\\"),
        ))

    total = query.count()
    rows = (
        query.options(joinedload(model.owner), joinedload(model.category_ref))
        .order_by(model.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    return {
        "items": [_listing_item(kind, row) for row in rows],
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": max(1, ceil(total / limit)) if total else 1,
    }


def _get(db: Session, kind: str, item_id: UUID, lock: bool = False):
    model = MODELS[kind]
    query = db.query(model).options(joinedload(model.owner), joinedload(model.category_ref)).filter(model.id == item_id)
    if lock:
        query = query.with_for_update(of=model).populate_existing()
    row = query.first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{WORDS[kind].capitalize()} not found")
    return row


def get_listing_detail(db: Session, kind: str, item_id: UUID) -> dict:
    row = _get(db, kind, item_id)
    if kind == "item":
        orders_count = db.query(func.count(Order.id)).filter(Order.listing_id == row.id).scalar()
    else:
        orders_count = db.query(func.count(Booking.id)).filter(Booking.service_id == row.id).scalar()
    remover = db.get(User, row.removed_by) if row.removed_by else None

    detail = _listing_item(kind, row)
    detail.update({
        "description": row.description,
        "images": _image_urls(row),
        "removed_by": _person(remover),
        "orders_count": orders_count,
    })
    return detail


def remove_listing(db: Session, kind: str, item_id: UUID, admin_id: UUID, reason: str, notify: bool) -> dict:
    reason = reason.strip()
    if len(reason) < 3:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Give a reason the seller will see")
    row = _get(db, kind, item_id, lock=True)
    if row.removed_at:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"This {WORDS[kind]} is already removed")

    row.removed_at = datetime.utcnow()
    row.removed_by = admin_id
    row.removal_reason = reason
    db.commit()

    word = WORDS[kind]
    create_notification(
        db, row.user_id,
        f"Your {word} \"{row.title}\" was removed by Junction: {reason}",
        type=NotificationType.system,
        link=DASHBOARD_LINKS[kind],
        email=False,  # the removed/restored email below says more, and the admin can skip it
    )
    owner = row.owner
    emailed = send_listing_removed_email(owner.email, owner.name, word, row.title, reason) if notify and owner else False
    log_event("warning", "admin", "admin.listing_removed", f"Admin removed a {word}",
              details={"kind": kind, "item_id": row.id, "title": row.title, "reason": reason, "emailed": emailed},
              user_id=admin_id)
    return get_listing_detail(db, kind, row.id)


def restore_listing(db: Session, kind: str, item_id: UUID, admin_id: UUID, notify: bool) -> dict:
    row = _get(db, kind, item_id, lock=True)
    if not row.removed_at:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"This {WORDS[kind]} isn't removed")

    previous_reason = row.removal_reason
    row.removed_at = None
    row.removed_by = None
    row.removal_reason = None
    db.commit()

    word = WORDS[kind]
    create_notification(
        db, row.user_id,
        f"Your {word} \"{row.title}\" has been restored and is visible again.",
        type=NotificationType.system,
        link=DASHBOARD_LINKS[kind],
        email=False,  # the removed/restored email below says more, and the admin can skip it
    )
    owner = row.owner
    emailed = send_listing_restored_email(owner.email, owner.name, word, row.title) if notify and owner else False
    log_event("info", "admin", "admin.listing_restored", f"Admin restored a {word}",
              details={"kind": kind, "item_id": row.id, "title": row.title,
                       "previous_reason": previous_reason, "emailed": emailed},
              user_id=admin_id)
    return get_listing_detail(db, kind, row.id)
