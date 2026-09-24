"""
Service for handling seller payouts.

Handles payout initiation and management for sellers.
"""

from sqlalchemy.orm import Session
from uuid import UUID
import httpx
from datetime import datetime, timedelta
from app.config import get_settings
from app.models.order import Order, OrderStatus
from app.models.transaction import Transaction, TransactionType, TransactionStatus
from app.schemas.transaction import TransactionCreate
from app.models.bank_account import BankAccount
from app.services.notification_service import create_notification
from app.services.email_service import send_payout_initiated_email, send_payout_scheduled_email
from app.services.transaction_service import create_transaction
from app.models.user import User
from uuid import UUID
import uuid

settings = get_settings()

async def initiate_seller_payout(db: Session, order_id: UUID) -> bool:
    try:
        from app.models.bank_account import BankAccount

        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            print(f"❌ Order not found: {order_id}")
            return False

        bank_account = db.query(BankAccount).filter(
            BankAccount.user_id == order.seller_id,
            BankAccount.is_default == True
        ).first()

        if not bank_account:
            print(f"❌ Seller {order.seller_id} has no default bank account")
            return False

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
                    "narration": f"Viciniti payout for order {order_id}",
                    "reference": reference,
                },
                headers={
                    "Authorization": f"Bearer {settings.FLUTTERWAVE_SECRET_KEY}",
                    "Content-Type": "application/json"
                }
            )

        data = response.json()

        if data.get("status") != "success":
            print(f"❌ Payout failed for order {order_id}: {data.get('message')}")
            return False

        # Record this payout as a Transaction
        create_transaction(db, TransactionCreate(
            user_id=order.seller_id,
            reference=reference,
            amount=payout_amount,
            fee=0,
            type=TransactionType.payout,
            order_id=order_id,
        ))
        transaction = db.query(Transaction).filter(Transaction.reference == reference).first()
        transaction.status = TransactionStatus.success
        db.commit()

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
        return True

    except Exception as e:
        print(f"❌ initiate_seller_payout error: {e}")
        return False
    
async def check_seller_payout_eligibility(db: Session, order_id: UUID) -> bool:
    """
    Verify the seller can receive a payout for this order.
    Called at buyer confirmation time to catch problems early —
    does NOT move any money.
    """
    from app.models.bank_account import BankAccount

    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        print(f"❌ Order not found: {order_id}")
        return False

    bank_account = db.query(BankAccount).filter(
        BankAccount.user_id == order.seller_id,
        BankAccount.is_default == True
    ).first()

    if not bank_account:
        print(f"❌ Seller {order.seller_id} has no default bank account")
        return False

    return True

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