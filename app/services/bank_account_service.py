from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from uuid import UUID
from app.models.bank_account import BankAccount
from app.schemas.bank_account import BankAccountCreate
from app.services.payment_service import reschedule_stuck_payouts
from app.services.log_service import log_event

def create_bank_account(db: Session, user_id: UUID, data: BankAccountCreate) -> BankAccount:
    existing_count = db.query(BankAccount).filter(
        BankAccount.user_id == user_id
    ).count()
    is_first_account = existing_count == 0

    if data.is_default:
        db.query(BankAccount).filter(
            BankAccount.user_id == user_id,
            BankAccount.is_default == True
        ).update({"is_default": False})

    will_be_default = data.is_default or is_first_account

    bank_account = BankAccount(
        user_id=user_id,
        bank_name=data.bank_name,
        bank_code=data.bank_code,
        account_number=data.account_number,
        account_name=data.account_name,
        is_default=will_be_default,
    )

    db.add(bank_account)
    db.commit()
    db.refresh(bank_account)
    log_event("info", "payout", "bank_account.added", "Payout bank account added",
              details={"bank_name": bank_account.bank_name, "account_number": bank_account.account_number,
                       "is_default": bank_account.is_default},
              user_id=user_id)

    if will_be_default:
        reschedule_stuck_payouts(db, user_id)

    return bank_account


def get_bank_accounts(db: Session, user_id: UUID):
    return db.query(BankAccount).filter(BankAccount.user_id == user_id).all()


def get_default_bank_account(db: Session, user_id: UUID):
    return db.query(BankAccount).filter(
        BankAccount.user_id == user_id,
        BankAccount.is_default == True
    ).first()


def delete_bank_account(db: Session, user_id: UUID, account_id: UUID):
    account = db.query(BankAccount).filter(
        BankAccount.id == account_id,
        BankAccount.user_id == user_id
    ).first()

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bank account not found"
        )

    db.delete(account)
    db.commit()
    log_event("info", "payout", "bank_account.removed", "Payout bank account removed",
              details={"bank_name": account.bank_name, "account_number": account.account_number},
              user_id=user_id)

def set_default_bank_account(db: Session, user_id: UUID, account_id: UUID):
    db.query(BankAccount).filter(
        BankAccount.user_id == user_id,
        BankAccount.is_default == True
    ).update({"is_default": False})

    account = db.query(BankAccount).filter(
        BankAccount.id == account_id,
        BankAccount.user_id == user_id
    ).first()

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bank account not found"
        )

    account.is_default = True
    db.commit()

    reschedule_stuck_payouts(db, user_id)