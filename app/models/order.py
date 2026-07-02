from sqlalchemy import Column, Float, DateTime, Enum, ForeignKey, String, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.orm import relationship
from app.database import Base
from datetime import datetime
import uuid
import enum

class OrderStatus(enum.Enum):
    pending = "pending"
    paid = "paid"            # Payment confirmed, awaiting seller fulfillment
    fulfilled = "fulfilled"  # Seller marked complete, awaiting buyer confirmation
    completed = "completed"  # Buyer confirmed receipt
    cancelled = "cancelled"
    disputed = "disputed"    # Chargeback filed

class Order(Base):
    __tablename__ = "orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    listing_id = Column(UUID(as_uuid=True), ForeignKey("listings.id"), nullable=False)
    buyer_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    seller_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    amount = Column(Float, nullable=False)
    fee = Column(Float, nullable=False)
    status = Column(Enum(OrderStatus), default=OrderStatus.pending)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Completion proof fields
    completion_photos = Column(JSON, default=[])  # List of photo URLs
    completion_notes = Column(String, nullable=True)  # Seller's description of work done
    completed_at = Column(DateTime, nullable=True)  # When seller marked complete
    buyer_accepted_at = Column(DateTime, nullable=True)  # When buyer confirmed completion

    # Relationships
    listing = relationship("Listing", backref="orders")
    buyer = relationship("User", foreign_keys=[buyer_id], backref="purchases")
    seller = relationship("User", foreign_keys=[seller_id], backref="sales")