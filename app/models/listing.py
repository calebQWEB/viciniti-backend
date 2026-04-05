from sqlalchemy import Column, String, Text, Float, DateTime, Enum, ARRAY, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base
from datetime import datetime
import uuid
import enum

class ListingStatus(enum.Enum):
    active = "active"
    sold = "sold"

class Listing(Base):
    __tablename__ = "listings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    price = Column(Float, nullable=False)
    category = Column(String, nullable=False)
    images = Column(ARRAY(JSON), default=[])
    status = Column(Enum(ListingStatus), default=ListingStatus.active)
    location = Column(String, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship
    owner = relationship("User", backref="listings")