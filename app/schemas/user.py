from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime
from uuid import UUID

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

# Schema for returning a user in responses
class UserResponse(UserBase):
    id: UUID
    avatar: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True