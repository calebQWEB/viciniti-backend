"""Queries and actions behind the admin Users pages: search, the full picture of one user, suspension."""
from datetime import datetime, timedelta
from math import ceil
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.models.app_log import AppLog
from app.models.bank_account import BankAccount
from app.models.listing import Listing, ListingStatus
from app.models.order import Order, OrderStatus
from app.models.review import Review
from app.models.service import Service, ServiceStatus
from app.models.user import User
from app.services.admin_order_service import MONEY_TAKEN_STATUSES, _order_item, _order_options
from app.services.email_service import send_account_reinstated_email, send_account_suspended_email
from app.services.log_service import log_event


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _counts_by_owner(db: Session, model, owner_column, user_ids) -> dict:
    rows = db.query(owner_column, func.count(model.id)).filter(owner_column.in_(user_ids)).group_by(owner_column)
    return dict(rows.all())


def _user_item(user: User, listings: dict, services: dict, orders: dict) -> dict:
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "avatar": user.avatar,
        "location": user.location,
        "intent": user.intent,
        "created_at": user.created_at,
        "is_admin": user.is_admin,
        "is_suspended": user.is_suspended,
        "suspended_at": user.suspended_at,
        "listings_count": listings.get(user.id, 0),
        "services_count": services.get(user.id, 0),
        "orders_count": orders.get(user.id, 0),
    }


def list_users(db: Session, page: int = 1, limit: int = 25, search: Optional[str] = None,
               user_filter: str = "all") -> dict:
    query = db.query(User)
    if user_filter == "suspended":
        query = query.filter(User.is_suspended.is_(True))
    elif user_filter == "admins":
        query = query.filter(User.is_admin.is_(True))
    elif user_filter == "new":
        query = query.filter(User.created_at >= datetime.utcnow() - timedelta(days=7))

    if search and search.strip():
        pattern = f"%{_escape_like(search.strip())}%"
        query = query.filter(or_(User.name.ilike(pattern, escape="\\"), User.email.ilike(pattern, escape="\\")))

    total = query.count()
    users = query.order_by(User.created_at.desc()).offset((page - 1) * limit).limit(limit).all()

    ids = [u.id for u in users]
    listings = _counts_by_owner(db, Listing, Listing.user_id, ids)
    services = _counts_by_owner(db, Service, Service.user_id, ids)
    # Orders on either side
    orders = {}
    for column in (Order.buyer_id, Order.seller_id):
        for user_id, count in _counts_by_owner(db, Order, column, ids).items():
            orders[user_id] = orders.get(user_id, 0) + count

    return {
        "items": [_user_item(u, listings, services, orders) for u in users],
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": max(1, ceil(total / limit)) if total else 1,
    }


def _get_user(db: Session, user_id: UUID) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


def _by_status(db: Session, model, user_id: UUID, statuses) -> dict:
    counts = {s.value: 0 for s in statuses}
    for item_status, count in (
        db.query(model.status, func.count(model.id)).filter(model.user_id == user_id).group_by(model.status)
    ):
        counts[item_status.value] = count
    return counts


def _side_totals(db: Session, column, user_id: UUID) -> dict:
    count = db.query(func.count(Order.id)).filter(column == user_id).scalar()
    value = db.query(func.coalesce(func.sum(Order.amount), 0)).filter(
        column == user_id, Order.status.in_(MONEY_TAKEN_STATUSES)
    ).scalar()
    return {"count": count, "value": float(value)}


def get_user_detail(db: Session, user_id: UUID) -> dict:
    user = _get_user(db, user_id)

    listings_by_status = _by_status(db, Listing, user.id, ListingStatus)
    services_by_status = _by_status(db, Service, user.id, ServiceStatus)
    as_buyer = _side_totals(db, Order.buyer_id, user.id)
    as_seller = _side_totals(db, Order.seller_id, user.id)
    disputes = db.query(func.count(Order.id)).filter(
        or_(Order.buyer_id == user.id, Order.seller_id == user.id), Order.status == OrderStatus.disputed
    ).scalar()
    rating_average, rating_count = db.query(func.avg(Review.rating), func.count(Review.id)).filter(
        Review.seller_id == user.id
    ).one()

    bank = (
        db.query(BankAccount)
        .filter(BankAccount.user_id == user.id, BankAccount.is_default.is_(True))
        .first()
    )
    recent_orders = (
        db.query(Order).options(*_order_options)
        .filter(or_(Order.buyer_id == user.id, Order.seller_id == user.id))
        .order_by(Order.created_at.desc())
        .limit(10)
        .all()
    )
    logs = (
        db.query(AppLog).options(joinedload(AppLog.user))
        .filter(AppLog.user_id == user.id)
        .order_by(AppLog.created_at.desc())
        .limit(20)
        .all()
    )
    suspender = db.get(User, user.suspended_by) if user.suspended_by else None

    detail = _user_item(
        user,
        {user.id: sum(listings_by_status.values())},
        {user.id: sum(services_by_status.values())},
        {user.id: as_buyer["count"] + as_seller["count"]},
    )
    detail.update({
        "onboarded_at": user.onboarded_at,
        "suspension_reason": user.suspension_reason,
        "suspension_note": user.suspension_note,
        "suspended_by": {"id": suspender.id, "name": suspender.name, "email": suspender.email} if suspender else None,
        "bank": {
            "bank_name": bank.bank_name,
            "account_name": bank.account_name,
            "account_last4": bank.account_number[-4:],
        } if bank else None,
        "listings_by_status": listings_by_status,
        "services_by_status": services_by_status,
        "as_buyer": as_buyer,
        "as_seller": as_seller,
        "disputes": disputes,
        "rating_average": round(float(rating_average), 2) if rating_average is not None else None,
        "rating_count": rating_count,
        "recent_orders": [_order_item(o) for o in recent_orders],
        "logs": logs,
    })
    return detail


def suspend_user(db: Session, user_id: UUID, admin_id: UUID, reason: str, note: Optional[str], notify: bool) -> dict:
    user = _get_user(db, user_id)
    reason = reason.strip()
    if len(reason) < 3:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Give a reason the user will see")
    if user.id == admin_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You can't suspend your own account")
    if user.is_admin:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Admins can't be suspended")
    if user.is_suspended:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This user is already suspended")

    user.is_suspended = True
    user.suspended_at = datetime.utcnow()
    user.suspended_by = admin_id
    user.suspension_reason = reason
    user.suspension_note = note.strip() if note and note.strip() else None
    db.commit()

    emailed = send_account_suspended_email(user.email, user.name, reason) if notify else False
    log_event("warning", "admin", "admin.user_suspended", "Admin suspended a user",
              details={"suspended_user_id": user.id, "reason": reason, "emailed": emailed}, user_id=admin_id)
    return get_user_detail(db, user.id)


def unsuspend_user(db: Session, user_id: UUID, admin_id: UUID, note: Optional[str], notify: bool) -> dict:
    user = _get_user(db, user_id)
    if not user.is_suspended:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This user isn't suspended")

    previous_reason = user.suspension_reason
    user.is_suspended = False
    user.suspended_at = None
    user.suspended_by = None
    user.suspension_reason = None
    user.suspension_note = None
    db.commit()

    emailed = send_account_reinstated_email(user.email, user.name) if notify else False
    log_event("info", "admin", "admin.user_unsuspended", "Admin lifted a suspension",
              details={"unsuspended_user_id": user.id, "previous_reason": previous_reason,
                       "note": note.strip() if note and note.strip() else None, "emailed": emailed},
              user_id=admin_id)
    return get_user_detail(db, user.id)
