from sqlalchemy import Column, Float, DateTime, Enum, ForeignKey, String, Boolean, Integer, text
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
    refunded = "refunded"    # Chargeback lost, buyer refunded

class Order(Base):
    __tablename__ = "orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    listing_id = Column(UUID(as_uuid=True), ForeignKey("listings.id"), nullable=True)
    service_id = Column(UUID(as_uuid=True), ForeignKey("services.id"), nullable=True)
    buyer_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    seller_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    amount = Column(Float, nullable=False)
    fee = Column(Float, nullable=False)
    status = Column(Enum(OrderStatus), default=OrderStatus.pending)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Completion proof fields
    completion_photos = Column(JSON, default=[])
    completion_notes = Column(String, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    buyer_accepted_at = Column(DateTime, nullable=True)
    payout_due_at = Column(DateTime, nullable=True)
    payout_completed_at = Column(DateTime, nullable=True)

    # Payout attempts, so a stuck payout shows why without digging through logs
    payout_attempts = Column(Integer, nullable=False, default=0, server_default=text("0"))
    payout_last_attempt_at = Column(DateTime, nullable=True)
    # None after a success; starts with PAYOUT_CRASH_PREFIX when the attempt crashed mid-way
    payout_last_error = Column(String, nullable=True)

    # Refunds an admin made outside the app (e.g. a payment that arrived after the order expired)
    refunded_at = Column(DateTime, nullable=True)
    refund_reference = Column(String, nullable=True)
    refund_note = Column(String, nullable=True)
    refunded_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    listing = relationship("Listing", backref="orders")
    service = relationship("Service", backref="orders")
    buyer = relationship("User", foreign_keys=[buyer_id], backref="purchases")
    seller = relationship("User", foreign_keys=[seller_id], backref="sales")