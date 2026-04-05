from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.user import UserCreate, UserResponse
from app.services.auth_services import register_user, login_user, hash_password
from app.models.user import User
from app.models.password_reset_token import PasswordResetToken
from app.services.email_service import send_password_reset_email
from datetime import datetime, timedelta
import secrets
from pydantic import BaseModel

router = APIRouter(prefix="/auth", tags=["Authentication"])

class LoginRequest(BaseModel):
    email: str
    password: str

class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

@router.post("/register", response_model=UserResponse)
def register(user_data: UserCreate, db: Session = Depends(get_db)):
    return register_user(db, user_data)

@router.post("/login")
def login(credentials: LoginRequest, db: Session = Depends(get_db)):
    return login_user(db, credentials.email, credentials.password)

# Forgot password — generate token and send email
@router.post("/forgot-password")
def forgot_password(
    data: ForgotPasswordRequest,
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == data.email).first()

    # Always return success even if email not found — prevents email enumeration
    if not user:
        return {"message": "If that email exists, a reset link has been sent."}

    # Block Google OAuth users
    if not user.password_hash:
        return {"message": "If that email exists, a reset link has been sent."}

    # Invalidate any existing unused tokens for this user
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.used == False
    ).delete()
    db.commit()

    # Generate a secure random token
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(hours=1)

    reset_token = PasswordResetToken(
        user_id=user.id,
        token=token,
        expires_at=expires_at,
    )
    db.add(reset_token)
    db.commit()

    # Send reset email
    send_password_reset_email(
        to=user.email,
        name=user.name,
        reset_token=token
    )

    return {"message": "If that email exists, a reset link has been sent."}


# Reset password — verify token and update password
@router.post("/reset-password")
def reset_password(
    data: ResetPasswordRequest,
    db: Session = Depends(get_db)
):
    # Find the token
    reset_token = db.query(PasswordResetToken).filter(
        PasswordResetToken.token == data.token,
        PasswordResetToken.used == False
    ).first()

    if not reset_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )

    # Check expiry
    if reset_token.expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token has expired. Please request a new one."
        )

    # Validate new password
    if len(data.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters"
        )

    # Update password
    user = db.query(User).filter(User.id == reset_token.user_id).first()
    user.password_hash = hash_password(data.new_password)

    # Mark token as used
    reset_token.used = True

    db.commit()

    return {"message": "Password reset successfully. You can now log in."}
