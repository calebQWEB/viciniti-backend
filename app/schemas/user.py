from pydantic import BaseModel, EmailStr
from typing import Literal, Optional
from datetime import datetime
from uuid import UUID

UserIntent = Literal["buy", "sell", "both"]

# Base schema - shared fields
class UserBase(BaseModel):
    name: str
    email: EmailStr
    bio: Optional[str] = None
    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

# Schema for registering a new user
class UserCreate(UserBase):
    password: Optional[str] = None
    google_id: Optional[str] = None

# Schema for changing password
class PasswordChange(BaseModel):
    current_password: str
    new_password: str

# Schema for updating a user
class UserUpdate(BaseModel):
    name: Optional[str] = None
    bio: Optional[str] = None
    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    avatar: Optional[str] = None
    intent: Optional[UserIntent] = None

# Schema for returning a user in responses
class UserResponse(UserBase):
    id: UUID
    avatar: Optional[str] = None
    created_at: datetime
    intent: Optional[UserIntent] = None
    # Null until the user finishes or skips the welcome flow
    onboarded_at: Optional[datetime] = None
    # Only on your own account (never on public profiles); unlocks the admin area
    is_admin: bool = False

    class Config:
        from_attributes = True

# What anyone can see about another user: no email, coordinates or onboarding details
class PublicUserResponse(BaseModel):
    id: UUID
    name: str
    avatar: Optional[str] = None
    bio: Optional[str] = None
    # Area name only, e.g. "Ikeja"
    location: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class UserSummary(BaseModel):
    id: UUID
    name: str
    avatar: Optional[str] = None

    class Config:
        from_attributes = True