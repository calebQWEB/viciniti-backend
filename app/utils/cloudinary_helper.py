import cloudinary
import cloudinary.uploader
from app.config import get_settings

settings = get_settings()

cloudinary.config(
    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
    api_key=settings.CLOUDINARY_API_KEY,
    api_secret=settings.CLOUDINARY_API_SECRET,
    secure=True
)

def upload_image(file_bytes: bytes, user_id: str, folder: str = "viciniti/listings") -> dict:
    """
    Uploads an image to Cloudinary and returns both the secure URL and public_id.
    - file_bytes: raw image bytes
    - user_id: used to organize uploads per user in Cloudinary
    - folder: base folder in Cloudinary
    """
    result = cloudinary.uploader.upload(
        file_bytes,
        folder=f"{folder}/{user_id}",
        resource_type="image"
    )
    return {
        "url": result["secure_url"],
        "public_id": result["public_id"]
    }