from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models.transaction import Transaction, TransactionStatus, TransactionType
from app.schemas.transaction import TransactionCreate, TransactionUpdate
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
    )
    db.add(new_transaction)
    db.commit()
    db.refresh(new_transaction)
    return new_transaction

def get_user_transactions(db: Session, user_id: UUID):
    return db.query(Transaction).filter(
        Transaction.user_id == UUID(str(user_id))
    ).order_by(Transaction.created_at.desc()).all()

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
        "redirect_url": "https://viciniti-frontend.vercel.app/payment/callback",
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

async def verify_payment(reference: str):
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

    return data["data"]["status"] == "successful"