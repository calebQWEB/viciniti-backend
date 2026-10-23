from datetime import date
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.app_log import (
    BulkResolveRequest, BulkResolveResponse, LogDetail, LogStatus, LogSummary, PaginatedLogs, ResolveRequest,
)
from app.schemas.admin import (
    AdminOrderDetail, AdminOverview, MarkRefundedRequest, OrderQueues, PaginatedAdminOrders, PayoutAttemptResult,
    RetryAllResult,
)
from app.services.admin_log_service import (
    bulk_resolve, get_log, get_summary, list_logs, reopen_log, resolve_log,
)
from app.services.admin_order_service import (
    get_order_detail, get_overview, get_queues, list_orders, mark_refunded, retry_failing_payouts, retry_payout,
)
from app.utils.security import require_admin

# Every route here is admin-only; non-admins get a 404
router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


# List logs, newest first, with filters
@router.get("/logs", response_model=PaginatedLogs)
def list_all(
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=100),
    level: Optional[List[str]] = Query(None),
    category: Optional[str] = None,
    event: Optional[str] = None,
    status: LogStatus = "all",
    user_id: Optional[UUID] = None,
    date_from: Optional[date] = Query(None, alias="from"),
    date_to: Optional[date] = Query(None, alias="to"),
    error_ref: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
):
    return list_logs(
        db, page=page, limit=limit, levels=level, category=category, event=event, status_filter=status,
        user_id=user_id, date_from=date_from, date_to=date_to, error_ref=error_ref, search=search,
    )


# Counts for the top of the dashboard
@router.get("/logs/summary", response_model=LogSummary)
def summary(db: Session = Depends(get_db)):
    return get_summary(db)


# Resolve many entries at once (by ids, or every open entry for one event)
@router.post("/logs/resolve-bulk", response_model=BulkResolveResponse)
def resolve_many(
    data: BulkResolveRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return {"resolved": bulk_resolve(db, admin.id, data.ids, data.event, data.note)}


# One entry in full
@router.get("/logs/{log_id}", response_model=LogDetail)
def get_one(log_id: UUID, db: Session = Depends(get_db)):
    return get_log(db, log_id)


@router.post("/logs/{log_id}/resolve", response_model=LogDetail)
def resolve(
    log_id: UUID,
    data: Optional[ResolveRequest] = None,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return resolve_log(db, log_id, admin.id, data.note if data else None)


@router.post("/logs/{log_id}/reopen", response_model=LogDetail)
def reopen(
    log_id: UUID,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return reopen_log(db, log_id, admin.id)


# ---------- Overview ----------

@router.get("/overview", response_model=AdminOverview)
def overview(db: Session = Depends(get_db)):
    return get_overview(db)


# ---------- Orders & money ----------

@router.get("/orders", response_model=PaginatedAdminOrders)
def orders(
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=100),
    search: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    return list_orders(db, page=page, limit=limit, search=search, status_filter=status)


# Failing and blocked payouts, refunds owed and open disputes
@router.get("/orders/queues", response_model=OrderQueues)
def order_queues(db: Session = Depends(get_db)):
    return get_queues(db)


# Retry every failing payout (up to 50), e.g. after fixing the Flutterwave setup
@router.post("/orders/retry-payouts", response_model=RetryAllResult)
async def retry_all_payouts(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return await retry_failing_payouts(db, admin.id)


@router.get("/orders/{order_id}", response_model=AdminOrderDetail)
def order_detail(order_id: UUID, db: Session = Depends(get_db)):
    return get_order_detail(db, order_id)


@router.post("/orders/{order_id}/retry-payout", response_model=PayoutAttemptResult)
async def retry_one_payout(order_id: UUID, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return await retry_payout(db, order_id, admin.id)


# Record a refund made outside the app (the buyer is notified)
@router.post("/orders/{order_id}/mark-refunded", response_model=AdminOrderDetail)
def refund(
    order_id: UUID,
    data: MarkRefundedRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return mark_refunded(db, order_id, admin.id, data.reference, data.note)
