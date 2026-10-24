from pydantic import BaseModel, Field
from typing import Dict, List, Literal, Optional
from datetime import date, datetime
from uuid import UUID

from app.schemas.app_log import LogListItem, LogUser

OrderQueue = Literal["failing_payouts", "blocked_payouts", "held_payouts", "refunds", "disputes"]


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
    held_payouts: List[AdminOrderItem]
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


# ---------- Users ----------

UserFilter = Literal["all", "suspended", "admins", "new"]


class AdminUserItem(BaseModel):
    id: UUID
    name: str
    email: str
    avatar: Optional[str] = None
    location: Optional[str] = None
    intent: Optional[str] = None
    created_at: Optional[datetime] = None
    is_admin: bool
    is_suspended: bool
    suspended_at: Optional[datetime] = None
    listings_count: int = 0
    services_count: int = 0
    orders_count: int = 0


class PaginatedAdminUsers(BaseModel):
    items: List[AdminUserItem]
    total: int
    page: int
    limit: int
    total_pages: int


class OrderSideTotals(BaseModel):
    count: int
    # Value of orders where the money was taken (paid onwards, not cancelled)
    value: float


class AdminUserDetail(AdminUserItem):
    onboarded_at: Optional[datetime] = None
    suspension_reason: Optional[str] = None
    suspension_note: Optional[str] = None
    suspended_by: Optional[LogUser] = None
    bank: Optional[SellerBank] = None
    listings_by_status: Dict[str, int]
    services_by_status: Dict[str, int]
    as_buyer: OrderSideTotals
    as_seller: OrderSideTotals
    disputes: int
    rating_average: Optional[float] = None
    rating_count: int = 0
    recent_orders: List[AdminOrderItem]
    logs: List[LogListItem]


class SuspendRequest(BaseModel):
    # Shown to the user on the login page and in the email
    reason: str = Field(min_length=3, max_length=500)
    # Admins only
    note: Optional[str] = Field(default=None, max_length=2000)
    notify: bool = True


class UnsuspendRequest(BaseModel):
    note: Optional[str] = Field(default=None, max_length=2000)
    notify: bool = True


# ---------- Listings & services ----------

ListingKind = Literal["item", "service"]


class ListingCategory(BaseModel):
    id: UUID
    name: str
    slug: str


class AdminListingItem(BaseModel):
    id: UUID
    kind: ListingKind
    title: str
    price: float
    # The seller's own status: active/sold for items, active/inactive for services
    status: str
    thumbnail: Optional[str] = None
    location: Optional[str] = None
    category: Optional[ListingCategory] = None
    seller: LogUser
    seller_suspended: bool = False
    created_at: Optional[datetime] = None
    removed_at: Optional[datetime] = None
    removal_reason: Optional[str] = None


class PaginatedAdminListings(BaseModel):
    items: List[AdminListingItem]
    total: int
    page: int
    limit: int
    total_pages: int


class AdminListingDetail(AdminListingItem):
    description: str
    images: List[str]
    removed_by: Optional[LogUser] = None
    # Orders for an item; bookings for a service
    orders_count: int


class RemoveListingRequest(BaseModel):
    # Shown to the seller
    reason: str = Field(min_length=3, max_length=500)
    notify: bool = True


class RestoreListingRequest(BaseModel):
    notify: bool = True


# ---------- Categories ----------

# Lucide icon names are kebab-case, e.g. "shopping-bag"
ICON_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"


class AdminCategory(BaseModel):
    id: UUID
    name: str
    slug: str
    type: ListingKind
    icon: Optional[str] = None
    sort_order: int
    is_active: bool
    # Listings or services filed under it
    usage_count: int


class CategoryCreate(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    type: ListingKind
    icon: Optional[str] = Field(default=None, max_length=50, pattern=ICON_PATTERN)


class CategoryUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=60)
    icon: Optional[str] = Field(default=None, max_length=50, pattern=ICON_PATTERN)
    is_active: Optional[bool] = None


class CategoryReorder(BaseModel):
    type: ListingKind
    # Every category of that type, in the new order
    ids: List[UUID]
