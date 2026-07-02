from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from uuid import UUID
from app.database import get_db
from app.utils.security import get_current_user
from app.schemas.bank_account import BankAccountCreate, BankAccountResponse, BankVerifyRequest
from app.services.bank_account_service import (
    create_bank_account,
    get_bank_accounts,
    delete_bank_account,
    set_default_bank_account
)
from typing import List
import httpx
from app.config import get_settings
from fastapi import HTTPException, status

settings = get_settings()

router = APIRouter(prefix="/bank-accounts", tags=["Bank Accounts"])


@router.post("/", response_model=BankAccountResponse)
def add_bank_account(
    data: BankAccountCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return create_bank_account(db, UUID(current_user["sub"]), data)


@router.get("/", response_model=List[BankAccountResponse])
def list_bank_accounts(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return get_bank_accounts(db, UUID(current_user["sub"]))


@router.delete("/{account_id}")
def remove_bank_account(
    account_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    delete_bank_account(db, UUID(current_user["sub"]), account_id)
    return {"status": "success", "message": "Bank account removed"}

@router.get("/banks")
async def list_banks():
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://api.flutterwave.com/v3/banks/NG",
            headers={
                "Authorization": f"Bearer {settings.FLUTTERWAVE_SECRET_KEY}",
            }
        )
    
    data = response.json()
    
    if data.get("status") != "success":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to fetch banks from Flutterwave"
        )
    
    return data["data"]

@router.post("/verify-account")
async def verify_bank_account(
    data: BankVerifyRequest,
    current_user: dict = Depends(get_current_user),
):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.flutterwave.com/v3/accounts/resolve",
            json={
                "account_number": data.account_number,
                "account_bank": data.bank_code,
            },
            headers={
                "Authorization": f"Bearer {settings.FLUTTERWAVE_SECRET_KEY}",
            }
        )
    
    result = response.json()
    
    if result.get("status") != "success":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not verify account. Please check the account number and bank."
        )
    
    return {
        "account_number": result["data"]["account_number"],
        "account_name": result["data"]["account_name"],
    }

@router.patch("/{account_id}/set-default")
def set_default(
    account_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    set_default_bank_account(db, UUID(current_user["sub"]), account_id)
    return {"status": "success", "message": "Default account updated"}