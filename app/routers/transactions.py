from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.transaction import TransactionResponse
from app.services.transaction_service import (
    get_user_transactions, get_transaction,
    initiate_payment, verify_payment,
    update_transaction_status, create_transaction
)
from app.services.notification_service import create_notification
from app.models.transaction import TransactionStatus, TransactionType, Transaction
from app.models.notification import Notification
from app.models.user import User
from app.schemas.transaction import TransactionCreate
from app.utils.security import get_current_user
from app.config import PLATFORM_FEE_PERCENTAGE
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel
from datetime import datetime, timedelta
import hashlib
import hmac
import json

router = APIRouter(prefix="/transactions", tags=["Transactions"])

class PaymentInitRequest(BaseModel):
    amount: float
    order_id: str

class PaymentVerifyRequest(BaseModel):
    reference: str

class FlutterwaveWebhookPayload(BaseModel):
    """Flutterwave webhook payload structure"""
    event: str
    data: dict
    
    class Config:
        extra = "allow"

# Helper function for notification deduplication
def create_notification_deduplicated(
    db: Session,
    user_id: UUID,
    message: str,
    transaction_reference: str,
    time_window_seconds: int = 10
) -> bool:
    """
    Create a notification only if a similar one doesn't already exist.
    
    Deduplication logic:
    - Check if notification with similar message exists
    - Only check within the last time_window_seconds
    - Prevents duplicate notifications from webhook + verify racing
    
    Returns: True if notification was created, False if deduplicated
    """
    cutoff_time = datetime.utcnow() - timedelta(seconds=time_window_seconds)
    
    # Check for existing notification with similar content
    existing = db.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.created_at >= cutoff_time,
        Notification.message.ilike(f"%payment%successful%")  # Match pattern
    ).first()
    
    if existing:
        print(f"ℹ️  Notification deduplication: Skipped for user {user_id} (already notified)")
        return False
    
    # No recent notification found, create new one
    create_notification(db, user_id, message)
    return True

router = APIRouter(prefix="/transactions", tags=["Transactions"])

class PaymentInitRequest(BaseModel):
    amount: float
    order_id: str

class PaymentVerifyRequest(BaseModel):
    reference: str

# Get all transactions for current user
@router.get("/", response_model=List[TransactionResponse])
def get_all(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return get_user_transactions(db, current_user["sub"])

# Get a single transaction
@router.get("/{transaction_id}", response_model=TransactionResponse)
def get_one(
    transaction_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return get_transaction(db, transaction_id)

# Initiate a payment
@router.post("/initiate-payment")
async def initiate(
    payment_data: PaymentInitRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == current_user["sub"]).first()

    result = await initiate_payment(
        amount=payment_data.amount,
        email=user.email,
        order_id=payment_data.order_id
    )

    fee = round(payment_data.amount * PLATFORM_FEE_PERCENTAGE, 2)
    create_transaction(db, TransactionCreate(
        user_id=user.id,
        reference=result["reference"],
        amount=payment_data.amount,
        fee=fee,
        type=TransactionType.payment,
        order_id=payment_data.order_id,
    ))

    return result

# Verify a payment
@router.post("/verify-payment")
async def verify(
    verify_data: PaymentVerifyRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Check that the transaction belongs to the current user
    transaction = db.query(Transaction).filter(
        Transaction.reference == verify_data.reference,
        Transaction.user_id == current_user["sub"]
    ).first()
    
    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized: Transaction not found"
        )
    
    is_verified = await verify_payment(verify_data.reference, transaction.order_id, db)

    if is_verified:
        transaction = update_transaction_status(
            db,
            verify_data.reference,
            TransactionStatus.success
        )

        # Use order_id from transaction to mark listing as sold
        if transaction.order_id:
            from app.models.order import Order, OrderStatus
            from app.models.listing import Listing, ListingStatus

            order = db.query(Order).filter(
                Order.id == transaction.order_id
            ).first()

            if order:
                # Mark listing as sold
                listing = db.query(Listing).filter(
                    Listing.id == order.listing_id
                ).first()
                if listing:
                    listing.status = ListingStatus.sold

                # Mark order as paid — awaiting seller fulfillment
                order.status = OrderStatus.paid
                db.commit()
                
                # Notify seller that payment was received
                create_notification_deduplicated(
                    db,
                    order.seller_id,
                    f"Payment received for your listing! New order from buyer.",
                    verify_data.reference,
                    time_window_seconds=10
                )

        create_notification_deduplicated(
            db,
            transaction.user_id,
            "Your payment was successful! 🎉",
            verify_data.reference,
            time_window_seconds=10
        )
        return {"status": "success", "message": "Payment verified successfully"}
    else:
        transaction = update_transaction_status(
            db,
            verify_data.reference,
            TransactionStatus.failed
        )
        
        # Cancel the associated order on payment failure
        if transaction.order_id:
            from app.models.order import Order, OrderStatus
            order = db.query(Order).filter(
                Order.id == transaction.order_id
            ).first()
            if order and order.status == OrderStatus.pending:
                order.status = OrderStatus.cancelled
                db.commit()
                
                create_notification(
                    db,
                    transaction.user_id,
                    "Payment verification failed. Your order has been cancelled."
                )
        
        return {"status": "failed", "message": "Payment verification failed"}

# Flutterwave Webhook endpoint
@router.post("/webhooks/flutterwave")
async def flutterwave_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Handle Flutterwave webhook events for payment updates.
    Flutterwave sends this when payment status changes on their end.
    
    Webhook signature is verified using HMAC-SHA256 to ensure
    the request actually came from Flutterwave (not a fake request).
    """
    from app.config import get_settings
    from app.models.order import Order, OrderStatus
    from app.models.listing import Listing, ListingStatus
    
    settings = get_settings()
    
    try:
        # Get raw request body for signature verification
        body = await request.body()
        
        # Get signature from Flutterwave header
        signature = request.headers.get("X-Flutterwave-Signature")
        
        if not signature:
            print("⚠️  Webhook received without signature header")
            raise HTTPException(
                status_code=403,
                detail="Missing X-Flutterwave-Signature header"
            )
        
        # Verify signature using Flutterwave's hash key
        # Flutterwave uses: HMAC-SHA256(body, FLUTTERWAVE_HASH_KEY)
        expected_signature = hmac.new(
            settings.FLUTTERWAVE_HASH_KEY.encode(),
            body,
            hashlib.sha256
        ).hexdigest()
        
        # Compare signatures (use constant-time comparison to prevent timing attacks)
        if not hmac.compare_digest(signature, expected_signature):
            print(f"❌ Invalid webhook signature. Expected: {expected_signature}, Got: {signature}")
            raise HTTPException(
                status_code=403,
                detail="Invalid webhook signature"
            )
        
        print("✅ Webhook signature verified")
        
        # Signature verified, parse the JSON payload
        payload_dict = json.loads(body.decode())
        payload = FlutterwaveWebhookPayload(**payload_dict)
        
        # Handle chargeback events
        if payload.event == "charge.dispute":
            from app.services.chargeback_service import (
                handle_chargeback_filed,
                handle_chargeback_won,
                handle_chargeback_lost
            )
            
            dispute_data = payload.data
            reference = dispute_data.get("tx_ref")
            dispute_reason = dispute_data.get("dispute_reason", "Unknown reason")
            dispute_status = dispute_data.get("dispute_status", "").lower()
            
            print(f"🔔 Chargeback event received for {reference}: {dispute_status}")
            
            # Route to appropriate handler based on status
            if dispute_status == "under_investigation":
                await handle_chargeback_filed(
                    db,
                    reference,
                    dispute_reason,
                    dispute_id=dispute_data.get("id")
                )
            elif dispute_status == "won":
                await handle_chargeback_won(db, reference)
            elif dispute_status == "lost":
                await handle_chargeback_lost(db, reference)
            
            return {"status": "success", "message": "Chargeback event processed"}
        
        # Only process successful payment events
        # Flutterwave sends: event="charge.completed" and data.status="successful"
        if payload.data.get("status") != "successful":
            return {"status": "ignored", "message": "Event status not successful"}
        
        reference = payload.data.get("tx_ref")
        
        if not reference:
            print("⚠️  Webhook missing transaction reference (tx_ref)")
            return {"status": "error", "message": "No transaction reference in payload"}
        
        # Find transaction by reference
        transaction = db.query(Transaction).filter(
            Transaction.reference == reference
        ).first()
        
        if not transaction:
            # This could happen if:
            # 1. Webhook arrived before our initiate_payment completed
            # 2. Reference doesn't match our pattern
            # 3. Transaction was deleted (shouldn't happen)
            print(f"⚠️  Webhook for unknown transaction reference: {reference}")
            return {"status": "error", "message": "Transaction not found"}
        
        # Idempotency check: If already processed, return success
        if transaction.status == TransactionStatus.success:
            print(f"ℹ️  Transaction {reference} already marked as success, skipping")
            return {"status": "success", "message": "Already processed"}
        
        # Update transaction status to success
        transaction.status = TransactionStatus.success
        
        # Update associated order if exists
        if transaction.order_id:
            order = db.query(Order).filter(
                Order.id == transaction.order_id
            ).first()
            
            if order and order.status == OrderStatus.pending:
                # Mark listing as sold
                listing = db.query(Listing).filter(
                    Listing.id == order.listing_id
                ).first()
                if listing:
                    listing.status = ListingStatus.sold

                # Mark order as paid — awaiting seller fulfillment
                order.status = OrderStatus.paid
                
                db.commit()
                
                print(f"✅ Payment confirmed for order {order.id}, awaiting seller fulfillment")
                
                # Notify seller that payment was received
                create_notification_deduplicated(
                    db,
                    order.seller_id,
                    f"Payment received! 🎉 Buyer has paid. Complete the work and upload proof.",
                    reference,
                    time_window_seconds=10
                )
        
        # Notify buyer
        create_notification_deduplicated(
            db,
            transaction.user_id,
            "Your payment was successful! 🎉",
            reference,
            time_window_seconds=10
        )
        
        db.commit()
        print(f"✅ Webhook processed successfully for transaction {reference}")
        
        return {"status": "success", "message": "Webhook processed"}
    
    except HTTPException:
        # Re-raise HTTP exceptions (like 403 for invalid signature)
        raise
    except Exception as e:
        print(f"❌ Error processing webhook: {str(e)}")
        # Return 500 so Flutterwave knows to retry
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )