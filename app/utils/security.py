from passlib.context import CryptContext
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID
from sqlalchemy.orm import Session
from app.config import get_settings
from app.database import get_db

settings = get_settings()

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

# JWT tokens
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def decode_access_token(token: str):
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None
    
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# Same as oauth2_scheme, but anonymous requests get None instead of a 401
optional_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

def get_optional_user(token: Optional[str] = Depends(optional_oauth2_scheme)):
    """The token payload for a logged-in request, or None (also for invalid tokens)."""
    return decode_access_token(token) if token else None

def get_current_user(token: str = Depends(oauth2_scheme)):
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload

def require_admin(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The admin's User row. Checked against the database on every request, so revoking admin takes effect at once.
    Non-admins get a 404, so the admin area doesn't reveal that it exists."""
    from app.models.user import User
    from app.services.log_service import log_event

    try:
        user = db.query(User).filter(User.id == UUID(str(current_user.get("sub")))).first()
    except ValueError:
        user = None
    if not user or not user.is_admin:
        log_event("warning", "admin", "admin.access_denied", "A non-admin tried to open the admin area",
                  user_id=user.id if user else None,
                  request_method=request.method, request_path=request.url.path, status_code=404)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    return user
