from math import ceil
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException, status
from app.models.transaction import Transaction, TransactionStatus, TransactionType
from app.schemas.transaction import TransactionCreate, TransactionUpdate
from app.models.order import Order
from app.config import get_settings
from uuid import UUID
import httpx
import uuid

settings = get_settings()

def create_transaction(db: Session, transaction_data: TransactionCreate):
    new_transaction = Transaction(
        user_id=transaction_data.user_id,
        reference=transaction_data.reference,
        amount=transaction_data.amount,
        fee=transaction_data.fee,
        type=transaction_data.type,
        order_id=transaction_data.order_id
    )
    db.add(new_transaction)
    db.commit()
    db.refresh(new_transaction)
    return new_transaction

def get_user_transactions(
    db: Session,
    user_id: UUID,
    page: int = 1,
    limit: int = 20,
    type_filter: Optional[str] = None,
    status_filter: Optional[str] = None,
):
    query = (
        db.query(Transaction)
        .options(
            joinedload(Transaction.order).joinedload(Order.listing),
            joinedload(Transaction.order).joinedload(Order.service),
        )
        .filter(Transaction.user_id == UUID(str(user_id)))
    )

    if type_filter and type_filter != "all":
        try:
            type_enum = TransactionType(type_filter)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid type filter: {type_filter}"
            )
        query = query.filter(Transaction.type == type_enum)

    if status_filter and status_filter != "all":
        try:
            status_enum = TransactionStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status filter: {status_filter}"
            )
        query = query.filter(Transaction.status == status_enum)

    total = query.count()

    items = (
        query.order_by(Transaction.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )

    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": max(1, ceil(total / limit)) if total else 1,
    }

def get_transaction(db: Session, transaction_id: UUID):
    transaction = db.query(Transaction).filter(
        Transaction.id == transaction_id
    ).first()
    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found"
        )
    return transaction

def update_transaction_status(db: Session, reference: str, new_status: TransactionStatus):
    transaction = db.query(Transaction).filter(
        Transaction.reference == reference
    ).first()
    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found"
        )
    transaction.status = new_status
    db.commit()
    db.refresh(transaction)
    return transaction

async def initiate_payment(amount: float, email: str, order_id: str):
    reference = f"VIC-{uuid.uuid4().hex[:8].upper()}"
    
    payload = {
        "tx_ref": reference,
        "amount": amount,
        "currency": "NGN",
        # "redirect_url": "https://viciniti-frontend.vercel.app/payment/callback",
        "redirect_url": f"{settings.FRONTEND_URL}/payment/callback",
        "customer": {
            "email": email,
        },
        "customizations": {
            "title": "Viciniti Payment",
            "description": f"Payment for order {order_id}",
        }
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.flutterwave.com/v3/payments",
            json=payload,
            headers={
                "Authorization": f"Bearer {settings.FLUTTERWAVE_SECRET_KEY}",
                "Content-Type": "application/json"
            }
        )

    data = response.json()
    print("Flutterwave Response", data)

    if data.get("status") != "success":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment initiation failed"
        )

    return {
        "reference": reference,
        "payment_link": data["data"]["link"]
    }

async def verify_payment(reference: str, order_id: UUID, db: Session):
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.flutterwave.com/v3/transactions/verify_by_reference?tx_ref={reference}",
                headers={
                    "Authorization": f"Bearer {settings.FLUTTERWAVE_SECRET_KEY}",
                }
            )

        data = response.json()

        if data.get("status") != "success":
            return False

        if data["data"]["status"] != "successful":
            return False

        # Fetch the order from the database
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            return False

        # Verify the amount Flutterwave charged matches the order amount
        flw_amount = data["data"]["amount"]
        flw_currency = data["data"]["currency"]

        if flw_currency != "NGN":
            print(f"❌ Currency mismatch: expected NGN, got {flw_currency}")
            return False

        if flw_amount < order.amount:
            print(f"❌ Amount mismatch: expected {order.amount}, got {flw_amount}")
            return False

        return True

    except Exception as e:
        print(f"❌ verify_payment error: {e}")
        return False

def get_transaction_stats(db: Session, user_id: UUID):
    uid = UUID(str(user_id))

    total_spent = (
        db.query(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(Transaction.user_id == uid, Transaction.type == TransactionType.payment, Transaction.status == TransactionStatus.success)
        .scalar()
    )
    total_earned = (
        db.query(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(Transaction.user_id == uid, Transaction.type == TransactionType.payout, Transaction.status == TransactionStatus.success)
        .scalar()
    )
    total_fees = (
        db.query(func.coalesce(func.sum(Transaction.fee), 0))
        .filter(Transaction.user_id == uid, Transaction.status == TransactionStatus.success)
        .scalar()
    )
    total_count = (
        db.query(func.count(Transaction.id))
        .filter(Transaction.user_id == uid, Transaction.status == TransactionStatus.success)
        .scalar()
    )

    return {
        "total_spent": float(total_spent),
        "total_earned": float(total_earned),
        "total_fees": float(total_fees),
        "total_transactions": total_count,
    }