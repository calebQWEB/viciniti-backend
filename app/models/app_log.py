from sqlalchemy import Column, String, Text, Integer, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base
from datetime import datetime
import uuid

# Kept as plain strings (not DB enums) so new levels or categories don't need a migration
LOG_LEVELS = ("info", "warning", "error", "critical")
LOG_CATEGORIES = (
    "auth", "listing", "order", "payment", "payout", "webhook",
    "chargeback", "booking", "email", "scheduler", "request", "admin",
)


class AppLog(Base):
    """Routine events and problems, recorded for the admin dashboard."""
    __tablename__ = "app_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    level = Column(String(16), nullable=False, index=True)
    category = Column(String(32), nullable=False, index=True)
    # Short machine name, e.g. "payment.confirmed" or "payout.failed"
    event = Column(String(64), nullable=False, index=True)
    message = Column(Text, nullable=False)
    # Context such as order_id, reference, amount (sensitive values are masked before saving)
    details = Column(JSON, nullable=True)

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # For request errors
    request_method = Column(String(8), nullable=True)
    request_path = Column(String(512), nullable=True)
    status_code = Column(Integer, nullable=True)
    # Shown to the user so they can quote it, e.g. "ERR-7F3A"
    error_ref = Column(String(16), nullable=True, index=True)
    traceback = Column(Text, nullable=True)

    # Whether a critical alert email went out for this entry
    alert_sent = Column(Boolean, default=False, nullable=False)

    # Admin workflow
    resolved_at = Column(DateTime, nullable=True)
    resolved_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolution_note = Column(Text, nullable=True)

    user = relationship("User", foreign_keys=[user_id])
    resolver = relationship("User", foreign_keys=[resolved_by])
