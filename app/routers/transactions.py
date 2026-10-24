from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy.orm import Session
from app.models.order import Order, OrderStatus
from app.config import UNPAID_ORDER_MINUTES
from app.database import get_db
from app.schemas.transaction import TransactionResponse
from app.services.transaction_service import (
    get_transaction_stats, get_user_transactions, get_transaction,
    initiate_payment, verify_payment,
    update_transaction_status, create_transaction
)
from app.services.notification_service import create_notification
from app.models.transaction import TransactionStatus, TransactionType, Transaction
from app.models.notification import Notification, NotificationType
from app.models.user import User
from app.schemas.transaction import TransactionCreate
from app.utils.security import get_current_user
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel
from datetime import datetime, timedelta
import hmac
import json
import logging
import traceback

from app.services.suspension import is_user_suspended
from app.services.log_service import log_event

logger = logging.getLogger("junction")

router = APIRouter(prefix="/transactions", tags=["Transactions"])

class PaymentInitRequest(BaseModel):
    order_id: str
    # Ignored: the charge always uses the order's own amount. Kept so existing clients still validate.
    amount: Optional[float] = None

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
        time_window_seconds: int = 10,
        type: Optional[NotificationType] = None,
        link: Optional[str] = None,
) -> bool:
    cutoff_time = datetime.utcnow() - timedelta(seconds=time_window_seconds)

    existing = db.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.created_at >= cutoff_time,
        Notification.message.ilike(f"%payment%successful%")
    ).first()

    if existing:
        logger.debug("Notification deduplication: skipped for user %s", user_id)
        return False

    create_notification(db, user_id, message, type=type, link=link)
    return True

LATE_PAYMENT_MESSAGE = (
    "We received your payment, but this order had already expired or been cancelled. "
    "Our team will refund you. You don't need to do anything."
)

def settle_paid_order(db: Session, transaction: Transaction, reference: str, seller_message: str,
                      source: str) -> str:
    """Apply a payment Flutterwave has confirmed to its order.

    Returns "paid", "already_paid", "needs_refund" (paid after the order expired or was
    cancelled, so there's nothing to sell) or "no_order".
    """
    from app.models.listing import Listing, ListingStatus

    order = (
        db.query(Order).filter(Order.id == transaction.order_id).first()
        if transaction.order_id else None
    )
    if not order:
        return "no_order"

    if order.status != OrderStatus.pending:
        if order.status in (OrderStatus.cancelled, OrderStatus.refunded):
            # Money was taken for an order we can't fulfil; flag it rather than reviving the order
            log_event("critical", "payment", "payment.needs_refund",
                      "Payment arrived for an expired or cancelled order and needs a manual refund",
                      details={"order_id": order.id, "reference": reference, "amount": transaction.amount,
                               "order_status": order.status.value, "source": source},
                      user_id=transaction.user_id)
            create_notification(
                db, transaction.user_id, LATE_PAYMENT_MESSAGE,
                type=NotificationType.payment, link="/dashboard/payments",
            )
            return "needs_refund"
        return "already_paid"

    listing = db.query(Listing).filter(Listing.id == order.listing_id).first()
    if listing:
        listing.status = ListingStatus.sold

    # Paid, awaiting seller fulfillment
    order.status = OrderStatus.paid
    db.commit()

    create_notification_deduplicated(
        db,
        order.seller_id,
        seller_message,
        reference,
        time_window_seconds=10,
        type=NotificationType.order,
        link=f"/dashboard/purchases?tab=sales&highlight={order.id}",
    )
    log_event("info", "payment", "payment.confirmed", "Payment confirmed",
              details={"order_id": order.id, "reference": reference, "amount": order.amount, "source": source},
              user_id=transaction.user_id)
    return "paid"

# Get all transactions for current user
@router.get("/")
def get_all(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return get_user_transactions(
        db, current_user["sub"], page=page, limit=limit, type_filter=type, status_filter=status
    )

@router.get("/stats")
def stats(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return get_transaction_stats(db, current_user["sub"])

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

    # Check the order before asking Flutterwave for a payment link
    order = db.query(Order).filter(Order.id == payment_data.order_id).first()
    # Someone else's order looks the same as a missing one
    if not order or str(order.buyer_id) != str(user.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )
    item = order.listing if order.listing_id else order.service
    if (
        order.status != OrderStatus.pending
        or is_user_suspended(db, order.seller_id)
        or (item is not None and item.removed_at is not None)
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This order can no longer be paid for."
        )
    if order.created_at < datetime.utcnow() - timedelta(minutes=UNPAID_ORDER_MINUTES):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This order has expired. Please start your purchase again."
        )
    if order.listing_id:
        from app.models.listing import Listing, ListingStatus
        listing = db.query(Listing).filter(Listing.id == order.listing_id).first()
        if not listing or listing.status != ListingStatus.active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This item has already been sold."
            )

    # Charge the order's own amount, never a figure sent by the browser
    result = await initiate_payment(
        amount=order.amount,
        email=user.email,
        order_id=payment_data.order_id
    )

    create_transaction(db, TransactionCreate(
        user_id=user.id,
        reference=result["reference"],
        amount=order.amount,
        fee=order.fee,
        type=TransactionType.payment,
        order_id=payment_data.order_id,
    ))
    log_event("info", "payment", "payment.started", "Buyer opened the payment page",
              details={"order_id": order.id, "reference": result["reference"], "amount": order.amount},
              user_id=user.id)

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

        outcome = settle_paid_order(
            db, transaction, verify_data.reference,
            "Payment received for your listing! New order from buyer.",
            source="redirect",
        )
        if outcome == "needs_refund":
            return {"status": "needs_refund", "message": LATE_PAYMENT_MESSAGE}

        create_notification_deduplicated(
            db,
            transaction.user_id,
            "Your payment was successful! 🎉",
            verify_data.reference,
            time_window_seconds=10,
            type=NotificationType.payment,
            link="/dashboard/payments",
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

    Flutterwave v3 proves a webhook is genuine by sending the dashboard "Secret hash"
    in the verif-hash header. To test locally (e.g. chargebacks), send that header
    with the value of FLUTTERWAVE_HASH_KEY.
    """
    from app.config import get_settings

    settings = get_settings()

    # Reject anything that doesn't carry our secret hash (constant-time comparison)
    received_hash = request.headers.get("verif-hash", "")
    if not received_hash or not hmac.compare_digest(received_hash, settings.FLUTTERWAVE_HASH_KEY):
        log_event("warning", "webhook", "webhook.rejected",
                  "Webhook rejected: missing or wrong verif-hash header",
                  details={"hash_present": bool(received_hash)},
                  request_method=request.method, request_path=request.url.path, status_code=401)
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        body = await request.body()
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
            
            logger.info("Chargeback event received for %s: %s", reference, dispute_status)
            
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
            log_event("warning", "webhook", "webhook.missing_reference",
                      "Successful-payment webhook without a transaction reference",
                      details={"event": payload.event})
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
            log_event("warning", "webhook", "webhook.unknown_reference",
                      "Webhook for a payment reference we don't recognise",
                      details={"reference": reference, "event": payload.event})
            return {"status": "error", "message": "Transaction not found"}
        
        # Idempotency check: If already processed, return success
        if transaction.status == TransactionStatus.success:
            logger.debug("Transaction %s already marked as success, skipping", reference)
            return {"status": "success", "message": "Already processed"}
        
        # Second layer: confirm with Flutterwave's API (status, amount, currency) before trusting it
        if not await verify_payment(reference, transaction.order_id, db):
            # verify_payment has already logged payment.unconfirmed with the reason
            logger.info("Webhook for %s not confirmed by Flutterwave's API, ignoring", reference)
            return {"status": "ignored", "message": "Payment not confirmed by Flutterwave"}

        transaction.status = TransactionStatus.success
        db.commit()

        outcome = settle_paid_order(
            db, transaction, reference,
            "Payment received! 🎉 Buyer has paid. Complete the work and upload proof.",
            source="webhook",
        )

        if outcome != "needs_refund":
            create_notification_deduplicated(
                db,
                transaction.user_id,
                "Your payment was successful! 🎉",
                reference,
                time_window_seconds=10,
                type=NotificationType.payment,
                link="/dashboard/payments",
            )

        db.commit()
        logger.debug("Webhook processed for transaction %s", reference)
        
        return {"status": "success", "message": "Webhook processed"}
    
    except HTTPException:
        # Re-raise HTTP exceptions (like 403 for invalid signature)
        raise
    except Exception as e:
        log_event("critical", "webhook", "webhook.processing_error",
                  f"A genuine webhook crashed while being processed: {type(e).__name__}: {e}",
                  traceback=traceback.format_exc(),
                  request_method=request.method, request_path=request.url.path, status_code=500)
        # Return 500 so Flutterwave knows to retry
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )