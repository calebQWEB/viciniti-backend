from sqlalchemy import Column, String, Text, Float, DateTime, Boolean, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base
from datetime import datetime
import uuid

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=True)  # nullable for Google OAuth users
    google_id = Column(String, nullable=True, unique=True)
    avatar = Column(String, nullable=True)
    bio = Column(Text, nullable=True)
    location = Column(String, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Onboarding: what the user came for ("buy", "sell" or "both"), and when they finished or skipped the welcome flow
    intent = Column(String, nullable=True)
    onboarded_at = Column(DateTime, nullable=True)

    # Grants the admin dashboard and critical error alert emails
    is_admin = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    # Suspension: locked out, listings and services hidden, payouts held. Nothing is deleted.
    is_suspended = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    suspended_at = Column(DateTime, nullable=True)
    suspended_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    # Shown to the user (login message and email)
    suspension_reason = Column(String, nullable=True)
    # Admins only
    suspension_note = Column(Text, nullable=True)
