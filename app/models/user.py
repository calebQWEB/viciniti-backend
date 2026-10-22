from sqlalchemy import Column, String, Text, Float, DateTime, Boolean, text
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