"""Queries and actions behind the admin Overview and Orders & money pages."""
from datetime import datetime, timedelta
from math import ceil
from typing import List, Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import String, and_, cast, exists, func, or_
from sqlalchemy.orm import Session, aliased, joinedload

from app.models.app_log import AppLog
from app.models.bank_account import BankAccount
from app.models.listing import Listing, ListingStatus
from app.models.notification import NotificationType
from app.models.order import Order, OrderStatus
from app.models.service import Service, ServiceStatus
from app.models.transaction import Transaction, TransactionStatus, TransactionType
from app.models.user import User
from app.services.log_service import log_event
from app.services.notification_service import create_notification
from app.services.payment_service import PAYOUT_CRASH_PREFIX, send_payout
from app.services.suspension import owner_not_suspended

QUEUE_LIMIT = 100
RETRY_ALL_LIMIT = 50

# Orders where the buyer's money was taken (and not handed back by a chargeback)
MONEY_TAKEN_STATUSES = (OrderStatus.paid, OrderStatus.fulfilled, OrderStatus.completed, OrderStatus.disputed)

_order_options = (
    joinedload(Order.listing),
    joinedload(Order.service),
    joinedload(Order.buyer),
    joinedload(Order.seller),
)


def _successful_payment(order_id_column):
    return exists().where(
        Transaction.order_id == order_id_column,
        Transaction.type == TransactionType.payment,
        Transaction.status == TransactionStatus.success,
    )


# ---------- Queue rules (shared by the queue lists, the counts and the action checks) ----------

def _failing_payouts_filter(now: datetime):
    return and_(
        Order.status == OrderStatus.completed,
        Order.payout_completed_at.is_(None),
        Order.payout_due_at.isnot(None),
        Order.payout_due_at <= now,
        owner_not_suspended(Order.seller_id),
    )


def _blocked_payouts_filter():
    return and_(
        Order.status == OrderStatus.completed,
        Order.payout_completed_at.is_(None),
        Order.payout_due_at.is_(None),
        owner_not_suspended(Order.seller_id),
    )


def _held_payouts_filter():
    # Seller suspended: nothing is paid out until an admin unsuspends them
    return and_(
        Order.status == OrderStatus.completed,
        Order.payout_completed_at.is_(None),
        ~owner_not_suspended(Order.seller_id),
    )


def _refunds_filter():
    # Paid after the order expired or was cancelled: the buyer is owed their money back
    return and_(
        Order.status == OrderStatus.cancelled,
        Order.refunded_at.is_(None),
        _successful_payment(Order.id),
    )


def _disputes_filter():
    return Order.status == OrderStatus.disputed


def _queue_filters(now: datetime) -> dict:
    return {
        "failing_payouts": _failing_payouts_filter(now),
        "blocked_payouts": _blocked_payouts_filter(),
        "held_payouts": _held_payouts_filter(),
        "refunds": _refunds_filter(),
        "disputes": _disputes_filter(),
    }


# ---------- Shaping ----------

def _party(user: Optional[User]) -> dict:
    if not user:
        return {"id": UUID(int=0), "name": "Deleted user", "email": ""}
    return {"id": user.id, "name": user.name, "email": user.email}


def _order_item(order: Order, payment: Optional[Transaction] = None) -> dict:
    is_listing = order.listing_id is not None
    item = order.listing if is_listing else order.service
    return {
        "id": order.id,
        "created_at": order.created_at,
        "status": order.status.value,
        "amount": order.amount,
        "fee": order.fee,
        "payout_amount": order.amount - order.fee,
        "item_title": item.title if item else ("Listing" if is_listing else "Service"),
        "item_type": "listing" if is_listing else "service",
        "buyer": _party(order.buyer),
        "seller": _party(order.seller),
        "payout_due_at": order.payout_due_at,
        "payout_completed_at": order.payout_completed_at,
        "payout_attempts": order.payout_attempts or 0,
        "payout_last_attempt_at": order.payout_last_attempt_at,
        "payout_last_error": order.payout_last_error,
        "payout_last_attempt_crashed": bool(
            order.payout_last_error and order.payout_last_error.startswith(PAYOUT_CRASH_PREFIX)
        ),
        "refunded_at": order.refunded_at,
        "payment_reference": payment.reference if payment else None,
        "dispute_reason": payment.chargeback_reason if payment else None,
        "dispute_filed_at": payment.chargeback_filed_at if payment else None,
    }


def _payments_by_order(db: Session, order_ids: List[UUID]) -> dict:
    """The buyer's payment transaction for each order (successful or disputed one preferred)."""
    if not order_ids:
        return {}
    rows = (
        db.query(Transaction)
        .filter(Transaction.order_id.in_(order_ids), Transaction.type == TransactionType.payment)
        .order_by(Transaction.created_at)
        .all()
    )
    found = {}
    for tx in rows:
        if tx.order_id not in found or tx.status != TransactionStatus.pending:
            found[tx.order_id] = tx
    return found


# ---------- Overview ----------

def _money_totals(db: Session, since: Optional[datetime]) -> dict:
    def window(column):
        return [column >= since] if since else []

    sales = db.query(func.coalesce(func.sum(Order.amount), 0)).filter(
        Order.status.in_(MONEY_TAKEN_STATUSES), *window(Order.created_at)
    ).scalar()
    fees = db.query(func.coalesce(func.sum(Order.fee), 0)).filter(
        Order.status == OrderStatus.completed, *window(Order.created_at)
    ).scalar()
    payouts_sent = db.query(func.coalesce(func.sum(Order.amount - Order.fee), 0)).filter(
        Order.payout_completed_at.isnot(None), *window(Order.payout_completed_at)
    ).scalar()
    return {"sales": float(sales), "fees": float(fees), "payouts_sent": float(payouts_sent)}


def get_overview(db: Session) -> dict:
    now = datetime.utcnow()
    month_ago = now - timedelta(days=30)

    by_status = {s.value: 0 for s in OrderStatus}
    for order_status, count in db.query(Order.status, func.count(Order.id)).group_by(Order.status):
        by_status[order_status.value] = count

    attention = {
        name: db.query(func.count(Order.id)).filter(rule).scalar()
        for name, rule in _queue_filters(now).items()
    }
    attention["critical_logs"] = (
        db.query(func.count(AppLog.id))
        .filter(AppLog.level == "critical", AppLog.resolved_at.is_(None))
        .scalar()
    )

    # Orders where money was taken, per day for the last 30 days (days with none are filled in)
    day = func.date(Order.created_at)
    rows = (
        db.query(day, func.count(Order.id), func.coalesce(func.sum(Order.amount), 0))
        .filter(Order.status.in_(MONEY_TAKEN_STATUSES), Order.created_at >= month_ago)
        .group_by(day)
        .all()
    )
    per_day = {d: (count, float(value)) for d, count, value in rows}
    today = now.date()
    daily = []
    for offset in range(29, -1, -1):
        d = today - timedelta(days=offset)
        count, value = per_day.get(d, (0, 0.0))
        daily.append({"day": d, "orders": count, "value": value})

    payouts_owed = db.query(func.coalesce(func.sum(Order.amount - Order.fee), 0)).filter(
        Order.status == OrderStatus.completed, Order.payout_completed_at.is_(None)
    ).scalar()

    return {
        "users_total": db.query(func.count(User.id)).scalar(),
        "users_new_7d": db.query(func.count(User.id)).filter(User.created_at >= now - timedelta(days=7)).scalar(),
        "listings_active": db.query(func.count(Listing.id)).filter(Listing.status == ListingStatus.active).scalar(),
        "services_active": db.query(func.count(Service.id)).filter(Service.status == ServiceStatus.active).scalar(),
        "orders_by_status": by_status,
        "last_30d": _money_totals(db, month_ago),
        "all_time": _money_totals(db, None),
        "payouts_owed": float(payouts_owed),
        "attention": attention,
        "daily": daily,
    }


# ---------- Search and queues ----------

def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def list_orders(db: Session, page: int = 1, limit: int = 25, search: Optional[str] = None,
                status_filter: Optional[str] = None) -> dict:
    buyer, seller = aliased(User), aliased(User)
    query = (
        db.query(Order)
        .join(buyer, Order.buyer_id == buyer.id)
        .join(seller, Order.seller_id == seller.id)
    )

    if status_filter:
        try:
            query = query.filter(Order.status == OrderStatus(status_filter))
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown status: {status_filter}")

    if search and search.strip():
        pattern = f"%{_escape_like(search.strip())}%"
        query = query.filter(or_(
            cast(Order.id, String).ilike(pattern, escape="\\"),
            buyer.name.ilike(pattern, escape="\\"),
            buyer.email.ilike(pattern, escape="\\"),
            seller.name.ilike(pattern, escape="\\"),
            seller.email.ilike(pattern, escape="\\"),
            exists().where(Transaction.order_id == Order.id, Transaction.reference.ilike(pattern, escape="\\")),
        ))

    total = query.count()
    orders = (
        query.options(*_order_options)
        .order_by(Order.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    return {
        "items": [_order_item(o) for o in orders],
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": max(1, ceil(total / limit)) if total else 1,
    }


def get_queues(db: Session) -> dict:
    now = datetime.utcnow()
    result, counts = {}, {}
    order_by = {
        "failing_payouts": Order.payout_due_at,
        "blocked_payouts": Order.buyer_accepted_at,
        "held_payouts": Order.buyer_accepted_at,
        "refunds": Order.created_at,
        "disputes": Order.created_at,
    }
    for name, rule in _queue_filters(now).items():
        counts[name] = db.query(func.count(Order.id)).filter(rule).scalar()
        orders = (
            db.query(Order).options(*_order_options).filter(rule)
            .order_by(order_by[name].asc().nullslast())
            .limit(QUEUE_LIMIT)
            .all()
        )
        payments = _payments_by_order(db, [o.id for o in orders]) if name in ("refunds", "disputes") else {}
        result[name] = [_order_item(o, payments.get(o.id)) for o in orders]
    result["counts"] = counts
    return result


# ---------- Detail ----------

def _get_order(db: Session, order_id: UUID) -> Order:
    order = db.query(Order).options(*_order_options).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return order


def _can_retry_payout(order: Order, now: datetime) -> bool:
    return (
        order.status == OrderStatus.completed
        and not (order.seller and order.seller.is_suspended)
        and order.payout_completed_at is None
        and order.payout_due_at is not None
        and order.payout_due_at <= now
    )


def _can_mark_refunded(order: Order, has_payment: bool) -> bool:
    return order.status == OrderStatus.cancelled and order.refunded_at is None and has_payment


def _timeline(order: Order, transactions: List[Transaction], logs: List[AppLog]) -> List[dict]:
    first_log = {}
    for entry in sorted(logs, key=lambda e: e.created_at):
        first_log.setdefault(entry.event, entry.created_at)

    payment = next((t for t in transactions if t.type == TransactionType.payment
                    and t.status != TransactionStatus.pending), None)
    steps = [{"label": "Order placed", "at": order.created_at}]

    if payment:
        steps.append({"label": "Payment received", "at": first_log.get("payment.confirmed") or payment.created_at,
                      "detail": payment.reference})
    if order.status == OrderStatus.cancelled:
        at = first_log.get("order.cancelled") or first_log.get("order.expired")
        steps.append({"label": "Cancelled" if "order.cancelled" in first_log else "Expired unpaid",
                      "at": at, "tone": "problem" if payment else "done"})
        if payment and not order.refunded_at:
            steps.append({"label": "Refund owed to the buyer", "tone": "problem",
                          "detail": "Payment arrived after the order was closed"})
    if order.completed_at:
        steps.append({"label": "Seller marked it fulfilled", "at": order.completed_at})
    if order.buyer_accepted_at:
        steps.append({"label": "Buyer confirmed", "at": order.buyer_accepted_at})

    if payment and payment.chargeback_filed_at:
        steps.append({"label": "Chargeback filed", "at": payment.chargeback_filed_at,
                      "detail": payment.chargeback_reason, "tone": "problem"})
        if payment.chargeback_resolved_at:
            won = payment.status == TransactionStatus.chargeback_won
            steps.append({"label": "Chargeback won" if won else "Chargeback lost",
                          "at": payment.chargeback_resolved_at, "tone": "done" if won else "problem"})

    if order.payout_completed_at:
        steps.append({"label": "Payout sent", "at": order.payout_completed_at})
    elif order.status == OrderStatus.completed:
        if order.payout_attempts and order.payout_last_error:
            steps.append({"label": f"Payout failed ({order.payout_attempts} attempt"
                                   f"{'' if order.payout_attempts == 1 else 's'})",
                          "at": order.payout_last_attempt_at, "detail": order.payout_last_error, "tone": "problem"})
        elif order.payout_due_at:
            steps.append({"label": "Payout due", "at": order.payout_due_at,
                          "tone": "upcoming" if order.payout_due_at > datetime.utcnow() else "problem"})
        else:
            steps.append({"label": "Payout blocked: seller has no bank account", "tone": "problem"})
        if order.seller and order.seller.is_suspended:
            steps.append({"label": "Payout held: seller is suspended", "tone": "problem"})

    if order.refunded_at:
        steps.append({"label": "Refunded by admin", "at": order.refunded_at, "detail": order.refund_reference})
    return steps


def get_order_detail(db: Session, order_id: UUID) -> dict:
    order = _get_order(db, order_id)
    transactions = (
        db.query(Transaction).filter(Transaction.order_id == order.id).order_by(Transaction.created_at).all()
    )
    logs = (
        db.query(AppLog)
        .options(joinedload(AppLog.user))
        .filter(AppLog.details["order_id"].as_string() == str(order.id))
        .order_by(AppLog.created_at.desc())
        .limit(100)
        .all()
    )
    bank = (
        db.query(BankAccount)
        .filter(BankAccount.user_id == order.seller_id, BankAccount.is_default.is_(True))
        .first()
    )
    refunder = db.get(User, order.refunded_by) if order.refunded_by else None
    payment = _payments_by_order(db, [order.id]).get(order.id)
    has_payment = any(t.type == TransactionType.payment and t.status == TransactionStatus.success
                      for t in transactions)

    detail = _order_item(order, payment)
    detail.update({
        "item_id": order.listing_id or order.service_id,
        "seller_bank": {
            "bank_name": bank.bank_name,
            "account_name": bank.account_name,
            "account_last4": bank.account_number[-4:],
        } if bank else None,
        "completion_photos": order.completion_photos or [],
        "completion_notes": order.completion_notes,
        "completed_at": order.completed_at,
        "buyer_accepted_at": order.buyer_accepted_at,
        "refund_reference": order.refund_reference,
        "refund_note": order.refund_note,
        "refunded_by": _party(refunder) if refunder else None,
        "transactions": [
            {
                "id": t.id, "reference": t.reference, "type": t.type.value, "status": t.status.value,
                "amount": t.amount, "fee": t.fee, "created_at": t.created_at,
                "chargeback_reason": t.chargeback_reason, "chargeback_filed_at": t.chargeback_filed_at,
                "chargeback_resolved_at": t.chargeback_resolved_at,
            }
            for t in transactions
        ],
        "timeline": _timeline(order, transactions, logs),
        "logs": logs,
        "can_retry_payout": _can_retry_payout(order, datetime.utcnow()),
        "can_mark_refunded": _can_mark_refunded(order, has_payment),
    })
    return detail


# ---------- Actions ----------

async def retry_payout(db: Session, order_id: UUID, admin_id: UUID) -> dict:
    order = _get_order(db, order_id)
    if not _can_retry_payout(order, datetime.utcnow()):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="This order has no payout due: it's not completed, not due yet, already paid, "
                                   "or the seller is suspended")
    db.rollback()  # start send_payout's locking transaction clean

    result = await send_payout(db, order_id)
    log_event("info", "admin", "admin.payout_retried",
              f"Admin retried a payout: {result.outcome}",
              details={"order_id": order_id, "ok": result.ok, "outcome": result.outcome, "message": result.message},
              user_id=admin_id)
    return {"order_id": order_id, "ok": result.ok, "outcome": result.outcome, "message": result.message}


async def retry_failing_payouts(db: Session, admin_id: UUID) -> dict:
    order_ids = [
        order_id for (order_id,) in
        db.query(Order.id).filter(_failing_payouts_filter(datetime.utcnow()))
        .order_by(Order.payout_due_at).limit(RETRY_ALL_LIMIT).all()
    ]
    db.rollback()

    results = []
    for order_id in order_ids:
        result = await send_payout(db, order_id)
        results.append({"order_id": order_id, "ok": result.ok, "outcome": result.outcome, "message": result.message})

    sent = sum(1 for r in results if r["ok"])
    if results:
        log_event("info", "admin", "admin.payouts_retried",
                  f"Admin retried {len(results)} failing payouts: {sent} sent",
                  details={"attempted": len(results), "sent": sent}, user_id=admin_id)
    return {"attempted": len(results), "sent": sent, "results": results}


def mark_refunded(db: Session, order_id: UUID, admin_id: UUID, reference: Optional[str], note: Optional[str]) -> dict:
    order = (
        db.query(Order).filter(Order.id == order_id).with_for_update().populate_existing().first()
    )
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    has_payment = db.query(_successful_payment(order.id)).scalar()
    if not _can_mark_refunded(order, has_payment):
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Only cancelled orders that took a payment can be marked refunded")

    order.status = OrderStatus.refunded
    order.refunded_at = datetime.utcnow()
    order.refunded_by = admin_id
    order.refund_reference = reference.strip() if reference and reference.strip() else None
    order.refund_note = note.strip() if note and note.strip() else None
    db.commit()

    create_notification(
        db,
        order.buyer_id,
        f"Your refund of ₦{order.amount:,.0f} for order #{str(order.id)[:8].upper()} has been sent. "
        f"It can take a few working days to reach your account.",
        type=NotificationType.payment,
        link="/dashboard/purchases",
    )
    log_event("info", "admin", "admin.order_refunded", "Admin recorded a manual refund",
              details={"order_id": order.id, "amount": order.amount, "reference": order.refund_reference},
              user_id=admin_id)
    return get_order_detail(db, order_id)
