"""Write routine events and problems to the app_logs table.

log_event() never raises: logging must not be able to break the request or job that called it.
It uses its own database session, so an entry survives even if the caller's transaction rolls back.
"""
import logging
import secrets
from datetime import datetime, timedelta
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import and_, or_

from app.database import SessionLocal
from app.models.app_log import AppLog, LOG_LEVELS

logger = logging.getLogger("junction")

# Swapped for the test database in tests/conftest.py
session_factory = SessionLocal

ALERT_THROTTLE = timedelta(hours=1)

# Retention: routine (info) entries are short-lived; problems are kept longer; unresolved ones are kept until resolved
INFO_RETENTION = timedelta(days=90)
ISSUE_RETENTION = timedelta(days=365)

# Keys whose values are never stored, and keys whose values keep only their last four characters
_REDACT_KEYS = ("password", "token", "secret", "authorization", "otp", "pin", "cvv", "api_key")
_MASK_KEYS = ("account_number", "card_number", "pan")


def new_error_ref() -> str:
    """Short reference a user can quote to support, e.g. 'ERR-7F3A'."""
    return f"ERR-{secrets.token_hex(2).upper()}"


def mask_email(email: Optional[str]) -> Optional[str]:
    """'tunde@example.com' -> 't***@example.com', for logs that need to say who without storing it."""
    if not email or "@" not in email:
        return email
    local, domain = email.split("@", 1)
    return f"{local[:1]}***@{domain}"


def _mask_last4(value: Any) -> str:
    text = str(value)
    return f"****{text[-4:]}" if len(text) > 4 else "****"


def sanitize(value: Any, key: str = "") -> Any:
    """Copy of value with secrets removed and account/card numbers masked, safe for JSON."""
    lowered = key.lower()
    if lowered and any(part in lowered for part in _REDACT_KEYS):
        return "[redacted]"
    if lowered and any(part in lowered for part in _MASK_KEYS):
        return _mask_last4(value)
    if isinstance(value, dict):
        return {str(k): sanitize(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize(v, key) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    # UUIDs, datetimes, Decimals, enums...
    return str(getattr(value, "value", value))


def _alert_failed_message(event: str) -> str:
    return f"Could not send the alert email for {event}"


def _send_alert_if_due(db, entry: AppLog) -> None:
    """Email admins about a critical entry, at most one attempt per event type per hour."""
    from app.models.user import User
    from app.services.email_service import send_admin_alert_email

    # A failed attempt counts too, so a broken mail setup doesn't retry on every critical event
    since = datetime.utcnow() - ALERT_THROTTLE
    recently_attempted = (
        db.query(AppLog.id)
        .filter(
            AppLog.created_at >= since,
            or_(
                and_(AppLog.event == entry.event, AppLog.alert_sent.is_(True)),
                and_(AppLog.event == "alert.failed", AppLog.message == _alert_failed_message(entry.event)),
            ),
        )
        .first()
    )
    if recently_attempted:
        return

    admins = db.query(User.email).filter(User.is_admin.is_(True)).all()
    if not admins:
        logger.warning("Critical event %s but no admins to alert", entry.event)
        return

    sent_any = False
    for (email,) in admins:
        sent_any |= send_admin_alert_email(
            to=email,
            event=entry.event,
            message=entry.message,
            details=entry.details or {},
            when=entry.created_at.strftime("%d %b %Y %H:%M"),
            error_ref=entry.error_ref,
        )

    if sent_any:
        entry.alert_sent = True
        db.commit()
    else:
        # Recorded as a plain warning so a broken mail setup can't trigger more alerts
        log_event("warning", "email", "alert.failed", _alert_failed_message(entry.event),
                  details={"log_id": str(entry.id), "event": entry.event})


def log_event(
    level: str,
    category: str,
    event: str,
    message: str,
    *,
    details: Optional[dict] = None,
    user_id: Optional[Any] = None,
    request_method: Optional[str] = None,
    request_path: Optional[str] = None,
    status_code: Optional[int] = None,
    error_ref: Optional[str] = None,
    traceback: Optional[str] = None,
) -> Optional[str]:
    """Record an event. Returns the new entry's id, or None if it couldn't be saved."""
    level = level if level in LOG_LEVELS else "error"
    clean_details = sanitize(details) if details else None

    # Always mirror to the console (Railway's logs) as well
    log_line = f"[{category}] {event}: {message}"
    getattr(logger, "warning" if level == "warning" else ("info" if level == "info" else "error"))(
        "%s %s", log_line, clean_details or ""
    )

    db = None
    try:
        db = session_factory()
        entry = AppLog(
            level=level,
            category=category,
            event=event,
            message=message,
            details=clean_details,
            user_id=UUID(str(user_id)) if user_id else None,
            request_method=request_method,
            request_path=request_path[:512] if request_path else None,
            status_code=status_code,
            error_ref=error_ref,
            traceback=traceback,
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)

        if level == "critical":
            try:
                _send_alert_if_due(db, entry)
            except Exception:
                logger.exception("Alert sending failed for %s", event)

        return str(entry.id)
    except Exception:
        logger.exception("Could not write log entry %s", log_line)
        return None
    finally:
        if db is not None:
            db.close()


def cleanup_old_logs(db) -> int:
    """Delete info entries past INFO_RETENTION and resolved issues past ISSUE_RETENTION. Returns rows deleted."""
    now = datetime.utcnow()
    deleted = (
        db.query(AppLog)
        .filter(AppLog.level == "info", AppLog.created_at < now - INFO_RETENTION)
        .delete(synchronize_session=False)
    )
    deleted += (
        db.query(AppLog)
        .filter(
            AppLog.level != "info",
            AppLog.created_at < now - ISSUE_RETENTION,
            AppLog.resolved_at.isnot(None),
        )
        .delete(synchronize_session=False)
    )
    db.commit()
    return deleted
