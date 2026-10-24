"""
Service for handling seller payouts.

Handles payout initiation and management for sellers.
"""

import logging
import traceback
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session
from uuid import UUID
import httpx
from datetime import datetime, timedelta
from app.config import BRAND_NAME, get_settings
from app.models.order import Order, OrderStatus
from app.models.transaction import Transaction, TransactionType, TransactionStatus
from app.models.bank_account import BankAccount
from app.services.notification_service import create_notification
from app.services.email_service import send_payout_initiated_email, send_payout_scheduled_email
from app.models.user import User
from app.models.notification import NotificationType
from app.services.log_service import log_event
import uuid

settings = get_settings()
logger = logging.getLogger("junction")

# payout_last_error starts with this when an attempt crashed part-way. The transfer may then have
# gone through without being recorded, so a retry needs a human check first.
PAYOUT_CRASH_PREFIX = "Crashed: "


@dataclass
class PayoutResult:
    ok: bool
    # sent | busy | not_found | not_payable | already_paid | seller_suspended | no_bank | rejected | crashed
    outcome: str
    message: str = ""


def _record_attempt(db: Session, order_id: UUID, error: Optional[str]) -> None:
    """Count a payout attempt on the order (in a fresh transaction, since the caller's may be broken)."""
    db.rollback()
    order = db.query(Order).filter(Order.id == order_id).first()
    if order:
        order.payout_attempts = (order.payout_attempts or 0) + 1
        order.payout_last_attempt_at = datetime.utcnow()
        order.payout_last_error = error
        db.commit()


async def send_payout(db: Session, order_id: UUID) -> PayoutResult:
    """Pay the seller for a completed order, at most once.

    The order row is locked for the whole attempt, so the hourly job and an admin retry can never
    both send money for the same order; whoever comes second gets "busy" or "already_paid".
    """
    try:
        from app.models.bank_account import BankAccount

        order = (
            db.query(Order)
            .filter(Order.id == order_id)
            .with_for_update(skip_locked=True)
            .populate_existing()
            .first()
        )
        if not order:
            if db.query(Order.id).filter(Order.id == order_id).first():
                return PayoutResult(False, "busy", "Another payout attempt for this order is in progress")
            log_event("error", "payout", "payout.failed", "Payout attempted for an order that doesn't exist",
                      details={"order_id": order_id})
            return PayoutResult(False, "not_found", "Order not found")

        if order.payout_completed_at:
            db.rollback()
            return PayoutResult(False, "already_paid", "This payout has already been sent")
        if order.status != OrderStatus.completed:
            status = order.status.value
            db.rollback()
            return PayoutResult(False, "not_payable", f"Order is {status}, not completed")
        if db.query(User.is_suspended).filter(User.id == order.seller_id).scalar():
            db.rollback()
            return PayoutResult(False, "seller_suspended", "Payout held: the seller is suspended")

        bank_account = db.query(BankAccount).filter(
            BankAccount.user_id == order.seller_id,
            BankAccount.is_default == True
        ).first()

        if not bank_account:
            log_event("warning", "payout", "payout.blocked_no_bank",
                      "Payout due but the seller has no bank account",
                      details={"order_id": order_id, "amount": order.amount - order.fee},
                      user_id=order.seller_id)
            message = "Seller has no default bank account"
            _record_attempt(db, order_id, message)
            return PayoutResult(False, "no_bank", message)

        payout_amount = order.amount - order.fee
        reference = f"PAYOUT-{uuid.uuid4().hex[:8].upper()}"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.flutterwave.com/v3/transfers",
                json={
                    "account_bank": bank_account.bank_code,
                    "account_number": bank_account.account_number,
                    "amount": payout_amount,
                    "currency": "NGN",
                    "narration": f"{BRAND_NAME} payout for order {order_id}",
                    "reference": reference,
                },
                headers={
                    "Authorization": f"Bearer {settings.FLUTTERWAVE_SECRET_KEY}",
                    "Content-Type": "application/json"
                }
            )

        data = response.json()

        if data.get("status") != "success":
            flutterwave_message = data.get("message") or "Flutterwave rejected the transfer"
            log_event("critical", "payout", "payout.failed", "Flutterwave rejected a seller payout",
                      details={"order_id": order_id, "amount": payout_amount, "reference": reference,
                               "flutterwave_message": data.get("message")},
                      user_id=order.seller_id)
            _record_attempt(db, order_id, flutterwave_message)
            return PayoutResult(False, "rejected", flutterwave_message)

        # Mark the order paid in the same commit that records the transfer, before the lock is released
        order.payout_completed_at = datetime.utcnow()
        order.payout_due_at = None
        order.payout_attempts = (order.payout_attempts or 0) + 1
        order.payout_last_attempt_at = order.payout_completed_at
        order.payout_last_error = None
        db.add(Transaction(
            user_id=order.seller_id,
            reference=reference,
            amount=payout_amount,
            fee=0,
            type=TransactionType.payout,
            status=TransactionStatus.success,
            order_id=order_id,
        ))
        db.commit()
        log_event("info", "payout", "payout.sent", "Seller payout sent",
                  details={"order_id": order_id, "amount": payout_amount, "reference": reference},
                  user_id=order.seller_id)

        create_notification(
            db,
            order.seller_id,
            f"🎉 Your payout of ₦{payout_amount:,.0f} has been initiated and will arrive in your account shortly.",
            type=NotificationType.payout,
            link="/dashboard/payments",
        )

        seller = db.query(User).filter(User.id == order.seller_id).first()
        if seller:
            send_payout_initiated_email(
                to=seller.email,
                name=seller.name,
                amount=payout_amount,
                account_name=bank_account.account_name,
                bank_name=bank_account.bank_name,
            )
        return PayoutResult(True, "sent", f"₦{payout_amount:,.0f} sent ({reference})")

    except Exception as e:
        error = f"{type(e).__name__}: {e}"
        log_event("critical", "payout", "payout.failed", f"Seller payout crashed: {error}",
                  details={"order_id": order_id}, traceback=traceback.format_exc())
        try:
            _record_attempt(db, order_id, f"{PAYOUT_CRASH_PREFIX}{error}"[:500])
        except Exception:
            logger.exception("Could not record the crashed payout attempt for %s", order_id)
        return PayoutResult(False, "crashed", error)


async def initiate_seller_payout(db: Session, order_id: UUID) -> bool:
    """True if the payout was sent. See send_payout for the details."""
    return (await send_payout(db, order_id)).ok


async def check_seller_payout_eligibility(db: Session, order_id: UUID) -> bool:
    """
    Verify the seller can receive a payout for this order.
    Called at buyer confirmation time to catch problems early —
    does NOT move any money.
    """
    from app.models.bank_account import BankAccount

    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        logger.debug("Payout eligibility check for unknown order %s", order_id)
        return False

    bank_account = db.query(BankAccount).filter(
        BankAccount.user_id == order.seller_id,
        BankAccount.is_default == True
    ).first()

    # The caller logs payout.blocked_no_bank when this is False
    return bank_account is not None

def reschedule_stuck_payouts(db: Session, seller_id: UUID):
    """
    Finds orders for this seller that are stuck — buyer already confirmed,
    but no payout was scheduled because there was no bank account at the time.
    Called whenever a seller gains a default bank account (new account, or
    promoting an existing one to default).
    """
    stuck_orders = db.query(Order).filter(
        Order.seller_id == seller_id,
        Order.status == OrderStatus.completed,
        Order.payout_due_at.is_(None)
    ).all()

    seller = db.query(User).filter(User.id == seller_id).first()

    for order in stuck_orders:
        order.payout_due_at = datetime.utcnow() + timedelta(days=3)

        create_notification(
            db,
            seller_id,
            f"✅ Your bank account is set up. Payment of ₦{order.amount:,.0f} "
            f"for order {order.id} will be released to your account in 3 days.",
            type=NotificationType.payout,
            link="/dashboard/payments",
        )

        if seller:
            send_payout_scheduled_email(
                to=seller.email,
                name=seller.name,
                amount=order.amount,
                order_id=str(order.id)
            )

    db.commit()