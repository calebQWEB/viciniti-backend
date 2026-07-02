from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional

class BankAccountBase(BaseModel):
    bank_name: str
    bank_code: str
    account_number: str
    account_name: str
    is_default: bool = False

class BankAccountCreate(BankAccountBase):
    pass

class BankAccountResponse(BankAccountBase):
    id: UUID
    user_id: UUID
    created_at: datetime

    class Config:
        from_attributes = True

class BankVerifyRequest(BaseModel):
    account_number: str
    bank_code: str