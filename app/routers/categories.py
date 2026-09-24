# app/routers/categories.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db
from app.schemas.category import CategoryResponse
from app.services.category_service import get_categories

router = APIRouter(prefix="/categories", tags=["Categories"])

@router.get("/", response_model=List[CategoryResponse])
def get_all(
        type: Optional[str] = Query(None, description="Filter by 'item' or 'service'"),
        db: Session = Depends(get_db)
):
    return get_categories(db, type_filter=type)