"""
Service for handling seller payouts.

Handles payout initiation and management for sellers.
"""

from sqlalchemy.orm import Session
from uuid import UUID
import httpx
from app.config import get_settings
from app.models.order import Order
from app.models.bank_account import BankAccount
from app.services.notification_service import create_notification
from app.services.email_service import send_payout_initiated_email
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

        # Fetch seller's default bank account
        bank_account = db.query(BankAccount).filter(
            BankAccount.user_id == order.seller_id,
            BankAccount.is_default == True
        ).first()

        if not bank_account:
            print(f"❌ Seller {order.seller_id} has no default bank account")
            return False

        # Calculate payout amount (order amount minus platform fee)
        payout_amount = order.amount - order.fee

        # Call Flutterwave Transfer API
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.flutterwave.com/v3/transfers",
                json={
                    "account_bank": bank_account.bank_code,
                    "account_number": bank_account.account_number,
                    "amount": payout_amount,
                    "currency": "NGN",
                    "narration": f"Viciniti payout for order {order_id}",
                    "reference": f"PAYOUT-{uuid.uuid4().hex[:8].upper()}",
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

        # Notify seller in-app
        create_notification(
            db,
            order.seller_id,
            f"🎉 Your payout of ₦{payout_amount:,.0f} has been initiated and will arrive in your account shortly."
        )

        # Send payout email to seller
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