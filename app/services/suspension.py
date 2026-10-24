"""What suspension and admin removal mean across the app: hidden from the public, locked, payouts held."""
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import and_, exists

from app.models.user import User

# The frontend looks for this start to show the suspension message on the login page
SUSPENDED_PREFIX = "This account has been suspended"


def suspended_message(reason: Optional[str]) -> str:
    because = f" Reason: {reason.strip().rstrip('.')}." if reason and reason.strip() else ""
    return f"{SUSPENDED_PREFIX}.{because} If you think this is a mistake, contact support."


def suspended_error(reason: Optional[str]) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=suspended_message(reason))


def owner_not_suspended(owner_id_column):
    """Filter for public queries: the row's owner (a user id column) isn't suspended."""
    return ~exists().where(User.id == owner_id_column, User.is_suspended.is_(True))


def is_user_suspended(db, user_id) -> bool:
    return bool(db.query(User.is_suspended).filter(User.id == user_id).scalar())


def publicly_visible(model):
    """Filter for public listing/service queries: not removed by an admin, and the owner isn't suspended."""
    return and_(model.removed_at.is_(None), owner_not_suspended(model.user_id))


def is_unavailable(db, item) -> bool:
    """A listing or service the public can't see or buy (removed, or its owner is suspended)."""
    return item.removed_at is not None or is_user_suspended(db, item.user_id)
