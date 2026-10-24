from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models.user import User
from app.schemas.user import UserCreate
from app.utils.security import hash_password, verify_password, create_access_token
from app.services.email_service import send_welcome_email, send_password_reset_email, send_new_message_email
from datetime import timedelta
from app.config import get_settings
from app.services.suspension import suspended_error
from app.services.log_service import log_event, mask_email

settings = get_settings()

def register_user(db: Session, user_data: UserCreate):
    # Check if email already exists
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Hash the password
    hashed = hash_password(user_data.password)

    # Create new user
    new_user = User(
        name=user_data.name,
        email=user_data.email,
        password_hash=hashed,
        bio=user_data.bio,
        location=user_data.location,
        latitude=user_data.latitude,
        longitude=user_data.longitude,
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    log_event("info", "auth", "auth.registered", "New account created", user_id=new_user.id)

    # Send welcome email
    send_welcome_email(to=new_user.email, name=new_user.name)

    return new_user

def login_user(db: Session, email: str, password: str):
    # Find user by email
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.password_hash):
        # Repeated failures can mean someone is guessing passwords
        log_event(
            "warning", "auth", "auth.login_failed", "Failed login attempt",
            details={"email": mask_email(email), "account_exists": user is not None},
            user_id=user.id if user else None,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Checked only after the password matches, so guessers don't learn the account is suspended
    if user.is_suspended:
        log_event("warning", "auth", "auth.login_suspended", "Suspended account tried to log in", user_id=user.id)
        raise suspended_error(user.suspension_reason)

    # Generate JWT token
    access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    log_event("info", "auth", "auth.login", "Logged in", user_id=user.id)

    return {"access_token": access_token, "token_type": "bearer"}