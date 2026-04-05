from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # Database
    DATABASE_URL: str

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

    # Google OAuth
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str

    # Resend Email api
    RESEND_API_KEY: str
    RESEND_FROM_EMAIL: str = "Viciniti <onboarding@resend.dev>"

    class Config:
        env_file = ".env"

@lru_cache()
def get_settings():
    return Settings()
