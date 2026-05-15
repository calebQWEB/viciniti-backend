from sqlalchemy import Column, String, Float, DateTime, Enum, ForeignKey, Boolean
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
    order_id = Column(UUID(as_uuid=True), nullable=True)  # ← links to order or booking
    reference = Column(String, unique=True, nullable=False)
    amount = Column(Float, nullable=False)
    fee = Column(Float, nullable=False)
    type = Column(Enum(TransactionType), nullable=False)
    status = Column(Enum(TransactionStatus), default=TransactionStatus.pending)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Chargeback fields
    chargeback_reason = Column(String, nullable=True)  # Reason from bank
    chargeback_filed_at = Column(DateTime, nullable=True)  # When chargeback was filed
    chargeback_evidence_notes = Column(String, nullable=True)  # Your response/evidence notes
    chargeback_resolved_at = Column(DateTime, nullable=True)  # When dispute was resolved
    
    # Terms acceptance tracking
    terms_accepted = Column(Boolean, default=True)
    terms_accepted_at = Column(DateTime, nullable=True)  # When buyer agreed to terms
    terms_version = Column(String, nullable=True)  # e.g. "v1.0"

    user = relationship("User", backref="transactions")