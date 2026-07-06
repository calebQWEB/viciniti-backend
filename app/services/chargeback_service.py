"""
Chargeback handling service.

Handles webhook events when customers file chargebacks against payments.
Updates transaction and order status, notifies both parties.
"""

from sqlalchemy.orm import Session
from uuid import UUID
import httpx
from datetime import datetime
from app.models.transaction import Transaction, TransactionStatus
from app.models.order import Order, OrderStatus
from app.models.user import User
from app.services.notification_service import create_notification
from app.config import CHARGEBACK_FEE, get_settings


settings = get_settings()

async def handle_chargeback_filed(
    db: Session,
    reference: str,
    reason: str,
    dispute_id: str = None
) -> bool:
    """
    Process incoming chargeback from Flutterwave webhook.
    
    Updates transaction and order status, notifies seller and buyer.
    
    Args:
        db: Database session
        reference: Transaction reference (e.g., "VIC-a1b2c3d4")
        reason: Chargeback reason from bank (e.g., "Unauthorized transaction")
        dispute_id: Flutterwave dispute ID (optional, for tracking)
    
    Returns:
        True if processed successfully, False if transaction not found
    """
    
    # Find the transaction
    transaction = db.query(Transaction).filter(
        Transaction.reference == reference
    ).first()
    
    if not transaction:
        print(f"❌ Chargeback for unknown transaction: {reference}")
        return False
    
    # Get the order
    order = db.query(Order).filter(
        Order.id == transaction.order_id
    ).first()
    
    if not order:
        print(f"❌ Chargeback transaction has no associated order: {reference}")
        return False
    
    # Update transaction status
    transaction.status = TransactionStatus.chargeback_filed
    transaction.chargeback_reason = reason
    transaction.chargeback_filed_at = datetime.utcnow()
    transaction.chargeback_id = dispute_id  # Store Flutterwave dispute ID
    
    # Mark order as disputed
    order.status = OrderStatus.disputed
    
    # Notify seller about the chargeback
    create_notification(
        db,
        order.seller_id,
        f"⚠️ CHARGEBACK ALERT: Payment for order {order.id} has been disputed by buyer. "
        f"Reason: {reason}. You have 7 days to provide evidence. "
        f"Check your dashboard for details."
    )
    
    # Notify buyer about the chargeback
    create_notification(
        db,
        order.buyer_id,
        f"⚠️ Payment dispute filed for order {order.id}. "
        f"Your bank is investigating this transaction. "
        f"Please check your email for updates from your bank."
    )
    
    # Commit changes
    db.commit()
    
    print(f"✅ Chargeback recorded for transaction {reference}")
    print(f"   Order: {order.id}")
    print(f"   Reason: {reason}")
    print(f"   Seller notified: {order.seller_id}")
    print(f"   Buyer notified: {order.buyer_id}")
    
    return True


async def handle_chargeback_won(
    db: Session,
    reference: str
) -> bool:
    """
    Process chargeback that was won (merchant prevails).
    
    Updates transaction status, notifies seller that they won.
    Funds stay with merchant.
    """
    
    transaction = db.query(Transaction).filter(
        Transaction.reference == reference
    ).first()
    
    if not transaction:
        print(f"❌ Chargeback win for unknown transaction: {reference}")
        return False
    
    order = db.query(Order).filter(
        Order.id == transaction.order_id
    ).first()
    
    # Update transaction
    transaction.status = TransactionStatus.chargeback_won
    transaction.chargeback_resolved_at = datetime.utcnow()

    # Move order back to completed
    if order:
        order.status = OrderStatus.completed
    
    # Notify seller - they won
    if order:
        create_notification(
            db,
            order.seller_id,
            f"✅ CHARGEBACK WON: The dispute for order {order.id} was resolved in your favor. "
            f"Payment of ₦{order.amount:,.0f} remains with you. Thank you for providing evidence!"
        )
    
    db.commit()
    
    print(f"✅ Chargeback won for transaction {reference}")
    
    return True


async def handle_chargeback_lost(
    db: Session,
    reference: str,
    refund_amount: float = None
) -> bool:
    """
    Process chargeback that was lost (customer prevails).
    
    Updates transaction status, notifies seller that they lost.
    Funds are reversed back to customer.
    """
    
    transaction = db.query(Transaction).filter(
        Transaction.reference == reference
    ).first()
    
    if not transaction:
        print(f"❌ Chargeback loss for unknown transaction: {reference}")
        return False
    
    order = db.query(Order).filter(
        Order.id == transaction.order_id
    ).first()
    
    # Update transaction
    transaction.status = TransactionStatus.chargeback_lost
    transaction.chargeback_resolved_at = datetime.utcnow()

    # Move order to refunded
    if order:
        order.status = OrderStatus.refunded
    
    # Notify seller - they lost
    if order:
        create_notification(
            db,
            order.seller_id,
            f"❌ CHARGEBACK LOST: The dispute for order {order.id} was resolved against you. "
            f"Payment of ₦{order.amount:,.0f} has been reversed to the buyer. "
            f"A chargeback fee of ₦{CHARGEBACK_FEE:,.0f} has been deducted from your account."
        )
    
    # Notify buyer - they won
    if order:
        create_notification(
            db,
            order.buyer_id,
            f"✅ Refund Processed: Your dispute for order {order.id} was successful. "
            f"₦{refund_amount or order.amount:,.0f} will be returned to your bank account "
            f"within 5-10 business days."
        )
    
    db.commit()
    
    print(f"❌ Chargeback lost for transaction {reference}")
    
    return True


async def submit_chargeback_evidence(
    db: Session,
    order_id: UUID,
    response_notes: str,
    evidence_photos: list = None
) -> bool:
    try:
        # Get transaction
        transaction = db.query(Transaction).filter(
            Transaction.order_id == order_id
        ).first()

        if not transaction:
            print(f"❌ No transaction found for order {order_id}")
            return False

        if not transaction.chargeback_id:
            print(f"❌ No chargeback ID found for transaction {transaction.id}")
            return False

        uploaded_proof_url = None

        # Step 1 — Upload proof photo if provided
        if evidence_photos and len(evidence_photos) > 0:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.flutterwave.com/v3/chargebacks/upload-proof",
                    json={"proof": evidence_photos[0]},
                    headers={
                        "Authorization": f"Bearer {settings.FLUTTERWAVE_SECRET_KEY}",
                        "Content-Type": "application/json"
                    }
                )
            data = response.json()
            if data.get("status") == "success":
                uploaded_proof_url = data.get("data")
                print(f"✅ Proof uploaded: {uploaded_proof_url}")
            else:
                print(f"⚠️ Proof upload failed: {data.get('message')}")

        # Step 2 — Decline the chargeback with evidence
        payload = {
            "status": "declined",
            "comment": response_notes,
        }
        if uploaded_proof_url:
            payload["uploaded_proof"] = uploaded_proof_url

        async with httpx.AsyncClient() as client:
            response = await client.put(
                f"https://api.flutterwave.com/v3/chargebacks/{transaction.chargeback_id}",
                json=payload,
                headers={
                    "Authorization": f"Bearer {settings.FLUTTERWAVE_SECRET_KEY}",
                    "Content-Type": "application/json"
                }
            )

        data = response.json()
        if data.get("status") != "success":
            print(f"❌ Chargeback decline failed: {data.get('message')}")
            return False

        print(f"✅ Chargeback evidence submitted for order {order_id}")
        return True

    except Exception as e:
        print(f"❌ submit_chargeback_evidence error: {e}")
        return False