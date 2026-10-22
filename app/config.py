from pydantic_settings import BaseSettings
from functools import lru_cache

# Platform name used in emails, payment labels and the API docs
BRAND_NAME = "Junction"

class Settings(BaseSettings):
    # Database
    DATABASE_URL: str

    # Environment
    ENVIRONMENT: str = "production"

    # JWT
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Cloudinary
    CLOUDINARY_CLOUD_NAME: str
    CLOUDINARY_API_KEY: str
    CLOUDINARY_API_SECRET: str

    # Flutterwave
    FLUTTERWAVE_PUBLIC_KEY: str
    FLUTTERWAVE_SECRET_KEY: str
    FLUTTERWAVE_HASH_KEY: str  # Used for webhook signature verification

    # Google OAuth
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str

    # Resend Email api
    RESEND_API_KEY: str
    RESEND_FROM_EMAIL: str = f"{BRAND_NAME} <onboarding@resend.dev>"
    FRONTEND_URL: str

    class Config:
        env_file = ".env"

# Platform fee configuration
PLATFORM_FEE_PERCENTAGE = 0.04
PLATFORM_FEE_CAP = 30000

def calculate_platform_fee(amount: float) -> float:
    return round(min(amount * PLATFORM_FEE_PERCENTAGE, PLATFORM_FEE_CAP), 2)

CHARGEBACK_FEE = 2500

# Unpaid orders hold a listing for this long; the scheduler cancels them after it
UNPAID_ORDER_MINUTES = 30

@lru_cache()
def get_settings():
    return Settings()
