from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.transaction import TransactionResponse
from app.services.transaction_service import (
    get_user_transactions, get_transaction,
    initiate_payment, verify_payment,
    update_transaction_status, create_transaction
)
from app.services.notification_service import create_notification
from app.models.transaction import TransactionStatus, TransactionType
from app.schemas.transaction import TransactionCreate
from app.utils.security import get_current_user
from app.models.user import User
from typing import List
from uuid import UUID
from pydantic import BaseModel

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

    fee = round(payment_data.amount * 0.05, 2)
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
    is_verified = await verify_payment(verify_data.reference)

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

                # Mark order as completed
                order.status = OrderStatus.completed
                db.commit()

        create_notification(
            db,
            transaction.user_id,
            "Your payment was successful! 🎉"
        )
        return {"status": "success", "message": "Payment verified successfully"}
    else:
        update_transaction_status(
            db,
            verify_data.reference,
            TransactionStatus.failed
        )
        return {"status": "failed", "message": "Payment verification failed"}