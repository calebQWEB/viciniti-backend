from pydantic import BaseModel, Field
from typing import Dict, List, Literal, Optional
from datetime import date, datetime
from uuid import UUID

from app.schemas.app_log import LogListItem, LogUser

OrderQueue = Literal["failing_payouts", "blocked_payouts", "refunds", "disputes"]


# ---------- Overview ----------

class MoneyTotals(BaseModel):
    # Value of orders where the buyer's money was taken
    sales: float
    # Fees on completed orders
    fees: float
    payouts_sent: float


class DailyOrders(BaseModel):
    day: date
    orders: int
    value: float


class AdminOverview(BaseModel):
    users_total: int
    users_new_7d: int
    listings_active: int
    services_active: int
    orders_by_status: Dict[str, int]
    last_30d: MoneyTotals
    all_time: MoneyTotals
    # Owed to sellers for completed orders, not yet paid out
    payouts_owed: float
    attention: Dict[str, int]
    daily: List[DailyOrders]


# ---------- Orders ----------

class OrderParty(LogUser):
    pass


class AdminOrderItem(BaseModel):
    id: UUID
    created_at: datetime
    status: str
    amount: float
    fee: float
    payout_amount: float
    item_title: str
    item_type: Literal["listing", "service"]
    buyer: OrderParty
    seller: OrderParty
    payout_due_at: Optional[datetime] = None
    payout_completed_at: Optional[datetime] = None
    payout_attempts: int = 0
    payout_last_attempt_at: Optional[datetime] = None
    payout_last_error: Optional[str] = None
    # True when the last attempt crashed part-way, so the transfer may have gone out unrecorded
    payout_last_attempt_crashed: bool = False
    refunded_at: Optional[datetime] = None
    # Set for the refund and dispute queues
    payment_reference: Optional[str] = None
    dispute_reason: Optional[str] = None
    dispute_filed_at: Optional[datetime] = None


class PaginatedAdminOrders(BaseModel):
    items: List[AdminOrderItem]
    total: int
    page: int
    limit: int
    total_pages: int


class OrderQueues(BaseModel):
    failing_payouts: List[AdminOrderItem]
    blocked_payouts: List[AdminOrderItem]
    refunds: List[AdminOrderItem]
    disputes: List[AdminOrderItem]
    counts: Dict[str, int]


class SellerBank(BaseModel):
    bank_name: str
    account_name: str
    # Last four digits only
    account_last4: str


class OrderTransaction(BaseModel):
    id: UUID
    reference: str
    type: str
    status: str
    amount: float
    fee: float
    created_at: Optional[datetime] = None
    chargeback_reason: Optional[str] = None
    chargeback_filed_at: Optional[datetime] = None
    chargeback_resolved_at: Optional[datetime] = None


class TimelineStep(BaseModel):
    label: str
    at: Optional[datetime] = None
    detail: Optional[str] = None
    # done | upcoming | problem
    tone: Literal["done", "upcoming", "problem"] = "done"


class AdminOrderDetail(AdminOrderItem):
    item_id: Optional[UUID] = None
    seller_bank: Optional[SellerBank] = None
    completion_photos: List[str] = []
    completion_notes: Optional[str] = None
    completed_at: Optional[datetime] = None
    buyer_accepted_at: Optional[datetime] = None
    refund_reference: Optional[str] = None
    refund_note: Optional[str] = None
    refunded_by: Optional[LogUser] = None
    transactions: List[OrderTransaction]
    timeline: List[TimelineStep]
    logs: List[LogListItem]
    # Which admin actions apply right now
    can_retry_payout: bool
    can_mark_refunded: bool


# ---------- Actions ----------

class PayoutAttemptResult(BaseModel):
    order_id: UUID
    ok: bool
    outcome: str
    message: str


class RetryAllResult(BaseModel):
    attempted: int
    sent: int
    results: List[PayoutAttemptResult]


class MarkRefundedRequest(BaseModel):
    reference: Optional[str] = Field(default=None, max_length=100)
    note: Optional[str] = Field(default=None, max_length=2000)
