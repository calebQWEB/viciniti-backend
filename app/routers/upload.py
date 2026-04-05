from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from app.utils.cloudinary_helper import upload_image
from app.utils.security import get_current_user

router = APIRouter(prefix="/upload", tags=["Upload"])

ALLOWED_TYPES = ["image/jpeg", "image/png", "image/webp"]
MAX_SIZE_BYTES = 5 * 1024 * 1024 # 5MB

@router.post("/image")
async def upload_single_image(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    # Validate file type
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Only JPEG, PNG and WebP are allowed."
        )
    
    # Read file bytes
    file_bytes = await file.read()

    # Validate file size
    if len(file_bytes) > MAX_SIZE_BYTES:
        raise HTTPException(
            status_code=400,
            detail="File too large. Maximum size is 5MB."
        )
    
    # Upload to Cloudinary
    result = upload_image(file_bytes, user_id=str(current_user["sub"]))

    return {
        "url": result["url"],
        "public_id": result["public_id"]
    }
