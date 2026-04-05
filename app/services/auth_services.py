from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models.user import User
from app.schemas.user import UserCreate
from app.utils.security import hash_password, verify_password, create_access_token
from app.services.email_service import send_welcome_email, send_password_reset_email, send_new_message_email
from datetime import timedelta
from app.config import get_settings

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

    # Send welcome email
    send_welcome_email(to=new_user.email, name=new_user.name)

    return new_user

def login_user(db: Session, email: str, password: str):
    # Find user by email
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    
    # Verify password
    if not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    
    # Generate JWT token
    access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    return {"access_token": access_token, "token_type": "bearer"}