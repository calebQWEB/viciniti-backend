from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from uuid import UUID
from app.models.transaction import TransactionType, TransactionStatus

class TransactionBase(BaseModel):
    amount: float
    fee: float
    type: TransactionType

class TransactionCreate(TransactionBase):
    user_id: UUID
    reference: str
    order_id: Optional[UUID] = None

class TransactionUpdate(BaseModel):
    status: Optional[TransactionStatus] = None

class TransactionOrderSummary(BaseModel):
    id: UUID
    item_title: str

    class Config:
        from_attributes = True

class TransactionResponse(TransactionBase):
    id: UUID
    user_id: UUID
    reference: str
    status: TransactionStatus
    created_at: datetime
    order_id: Optional[UUID] = None
    order_summary: Optional[TransactionOrderSummary] = None

    class Config:
        from_attributes = True
