from sqlalchemy import Column, String, Float, DateTime, Enum, ForeignKey, Boolean, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base
from datetime import datetime
import uuid
import enum

class TransactionType(enum.Enum):
    payment = "payment"
    payout = "payout"

class TransactionStatus(enum.Enum):
    pending = "pending"
    success = "success"
    failed = "failed"
    chargeback_filed = "chargeback_filed"
    chargeback_won = "chargeback_won"
    chargeback_lost = "chargeback_lost"

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=True)
    reference = Column(String, unique=True, nullable=False)
    amount = Column(Float, nullable=False)
    fee = Column(Float, nullable=False)
    type = Column(Enum(TransactionType), nullable=False)
    status = Column(Enum(TransactionStatus), default=TransactionStatus.pending)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Chargeback fields
    chargeback_id = Column(String, nullable=True)
    chargeback_reason = Column(String, nullable=True)
    chargeback_filed_at = Column(DateTime, nullable=True)
    chargeback_evidence_notes = Column(String, nullable=True)
    chargeback_evidence_photos = Column(JSON, default=[])
    chargeback_resolved_at = Column(DateTime, nullable=True)

    # Terms acceptance tracking
    terms_accepted = Column(Boolean, default=True)
    terms_accepted_at = Column(DateTime, nullable=True)
    terms_version = Column(String, nullable=True)

    user = relationship("User", backref="transactions")
    order = relationship("Order", backref="transactions")

    @property
    def order_summary(self):
        if not self.order:
            return None
        title = self.order.listing.title if self.order.listing else (self.order.service.title if self.order.service else "Item")
        return {"id": self.order.id, "item_title": title}