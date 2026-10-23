"""Queries behind the admin logs API: listing, summary counts and resolving entries."""
from datetime import date, datetime, timedelta
from math import ceil
from typing import List, Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.models.app_log import AppLog
from app.services.log_service import log_event

ISSUE_LEVELS = ("warning", "error", "critical")
BULK_RESOLVE_LIMIT = 500
TOP_PROBLEMS = 5


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def list_logs(
    db: Session,
    page: int = 1,
    limit: int = 25,
    levels: Optional[List[str]] = None,
    category: Optional[str] = None,
    event: Optional[str] = None,
    status_filter: str = "all",
    user_id: Optional[UUID] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    error_ref: Optional[str] = None,
    search: Optional[str] = None,
):
    query = db.query(AppLog)

    if levels:
        query = query.filter(AppLog.level.in_(levels))
    if category:
        query = query.filter(AppLog.category == category)
    if event:
        query = query.filter(AppLog.event == event)
    # "open" means a problem nobody has resolved yet; routine info entries are never open
    if status_filter == "open":
        query = query.filter(AppLog.level.in_(ISSUE_LEVELS), AppLog.resolved_at.is_(None))
    elif status_filter == "resolved":
        query = query.filter(AppLog.resolved_at.isnot(None))
    if user_id:
        query = query.filter(AppLog.user_id == user_id)
    # Both dates are inclusive whole days
    if date_from:
        query = query.filter(AppLog.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        query = query.filter(AppLog.created_at < datetime.combine(date_to + timedelta(days=1), datetime.min.time()))
    if error_ref:
        query = query.filter(func.upper(AppLog.error_ref) == error_ref.strip().upper())
    if search:
        pattern = f"%{_escape_like(search.strip())}%"
        query = query.filter(or_(
            AppLog.message.ilike(pattern, escape="\\"),
            AppLog.event.ilike(pattern, escape="\\"),
            AppLog.error_ref.ilike(pattern, escape="\\"),
        ))

    total = query.count()
    items = (
        query.options(joinedload(AppLog.user))
        .order_by(AppLog.created_at.desc())
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


def _counts_by_level(db: Session, *filters) -> dict:
    rows = db.query(AppLog.level, func.count(AppLog.id)).filter(*filters).group_by(AppLog.level).all()
    return {level: count for level, count in rows}


def get_summary(db: Session) -> dict:
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)

    # Grouped by event so 40 identical failures show as one line
    top = (
        db.query(AppLog.event, AppLog.level, func.count(AppLog.id), func.max(AppLog.created_at))
        .filter(AppLog.level.in_(ISSUE_LEVELS), AppLog.created_at >= week_ago)
        .group_by(AppLog.event, AppLog.level)
        .order_by(func.count(AppLog.id).desc(), func.max(AppLog.created_at).desc())
        .limit(TOP_PROBLEMS)
        .all()
    )

    return {
        "open": _counts_by_level(db, AppLog.level.in_(ISSUE_LEVELS), AppLog.resolved_at.is_(None)),
        "last_24h": _counts_by_level(db, AppLog.created_at >= now - timedelta(hours=24)),
        "last_7d": _counts_by_level(db, AppLog.created_at >= week_ago),
        "top_problems": [
            {"event": event, "level": level, "count": count, "last_seen": last_seen}
            for event, level, count, last_seen in top
        ],
    }


def get_log(db: Session, log_id: UUID) -> AppLog:
    entry = (
        db.query(AppLog)
        .options(joinedload(AppLog.user), joinedload(AppLog.resolver))
        .filter(AppLog.id == log_id)
        .first()
    )
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Log entry not found")
    return entry


def resolve_log(db: Session, log_id: UUID, admin_id: UUID, note: Optional[str]) -> AppLog:
    entry = get_log(db, log_id)
    if entry.level == "info":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Routine info entries can't be resolved")

    entry.resolved_at = datetime.utcnow()
    entry.resolved_by = admin_id
    entry.resolution_note = note.strip() if note and note.strip() else None
    db.commit()
    log_event("info", "admin", "admin.log_resolved", "Admin resolved a log entry",
              details={"log_id": entry.id, "event": entry.event}, user_id=admin_id)
    return get_log(db, log_id)


def reopen_log(db: Session, log_id: UUID, admin_id: UUID) -> AppLog:
    entry = get_log(db, log_id)
    if not entry.resolved_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This entry isn't resolved")

    entry.resolved_at = None
    entry.resolved_by = None
    entry.resolution_note = None
    db.commit()
    log_event("info", "admin", "admin.log_reopened", "Admin reopened a log entry",
              details={"log_id": entry.id, "event": entry.event}, user_id=admin_id)
    return get_log(db, log_id)


def bulk_resolve(
    db: Session, admin_id: UUID, ids: Optional[List[UUID]], event: Optional[str], note: Optional[str]
) -> int:
    if bool(ids) == bool(event):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Send either a list of ids or an event, not both")

    query = db.query(AppLog).filter(AppLog.level.in_(ISSUE_LEVELS), AppLog.resolved_at.is_(None))
    query = query.filter(AppLog.id.in_(ids)) if ids else query.filter(AppLog.event == event)
    entries = query.order_by(AppLog.created_at).limit(BULK_RESOLVE_LIMIT).all()

    now = datetime.utcnow()
    clean_note = note.strip() if note and note.strip() else None
    for entry in entries:
        entry.resolved_at = now
        entry.resolved_by = admin_id
        entry.resolution_note = clean_note
    db.commit()

    if entries:
        log_event("info", "admin", "admin.logs_bulk_resolved", f"Admin resolved {len(entries)} log entries",
                  details={"count": len(entries), "event": event, "by_ids": bool(ids)}, user_id=admin_id)
    return len(entries)
