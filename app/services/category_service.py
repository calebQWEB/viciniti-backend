# app/services/category_service.py
from sqlalchemy.orm import Session
from app.models.category import Category, CategoryType
from typing import Optional

def get_categories(db: Session, type_filter: Optional[str] = None):
    query = db.query(Category).filter(Category.is_active == True)
    if type_filter:
        query = query.filter(Category.type == CategoryType(type_filter))
    return query.order_by(Category.sort_order).all()