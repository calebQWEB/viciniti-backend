"""Admin management of categories: add, rename, re-icon, reorder, retire, delete when unused."""
import re
from typing import List, Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.category import Category, CategoryType
from app.models.listing import Listing
from app.models.service import Service
from app.services.log_service import log_event


def slugify(name: str) -> str:
    """'Phones & Tablets' -> 'phones-tablets'. Fixed once created, so links to it keep working."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _usage_counts(db: Session) -> dict:
    counts = {}
    for model in (Listing, Service):
        for category_id, count in (
            db.query(model.category_id, func.count(model.id))
            .filter(model.category_id.isnot(None))
            .group_by(model.category_id)
        ):
            counts[category_id] = counts.get(category_id, 0) + count
    return counts


def _shape(category: Category, usage: dict) -> dict:
    return {
        "id": category.id,
        "name": category.name,
        "slug": category.slug,
        "type": category.type.value,
        "icon": category.icon,
        "sort_order": category.sort_order or 0,
        "is_active": bool(category.is_active),
        "usage_count": usage.get(category.id, 0),
    }


def list_categories(db: Session) -> List[dict]:
    usage = _usage_counts(db)
    rows = db.query(Category).order_by(Category.type, Category.sort_order, Category.name).all()
    return [_shape(c, usage) for c in rows]


def _get(db: Session, category_id: UUID) -> Category:
    category = db.get(Category, category_id)
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    return category


def create_category(db: Session, admin_id: UUID, name: str, kind: str, icon: Optional[str]) -> dict:
    name = name.strip()
    slug = slugify(name)
    if len(slug) < 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Use a name with letters or numbers")
    if db.query(Category.id).filter(Category.slug == slug).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"A category with the web name \"{slug}\" already exists")

    category_type = CategoryType(kind)
    last = db.query(func.max(Category.sort_order)).filter(Category.type == category_type).scalar()
    category = Category(name=name, slug=slug, type=category_type, icon=icon,
                        sort_order=(last if last is not None else -1) + 1, is_active=True)
    db.add(category)
    db.commit()
    log_event("info", "admin", "admin.category_created", "Admin added a category",
              details={"category_id": category.id, "name": name, "slug": slug, "type": kind}, user_id=admin_id)
    return _shape(category, {})


def update_category(db: Session, admin_id: UUID, category_id: UUID, changes: dict) -> dict:
    category = _get(db, category_id)
    if "name" in changes and changes["name"] is not None:
        changes["name"] = changes["name"].strip()
        if len(changes["name"]) < 2:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Name is too short")
    applied = {}
    for field in ("name", "icon", "is_active"):
        if field in changes and (changes[field] is not None or field == "icon"):
            setattr(category, field, changes[field])
            applied[field] = changes[field]
    db.commit()

    event = "admin.category_updated"
    if applied.keys() == {"is_active"}:
        event = "admin.category_reactivated" if applied["is_active"] else "admin.category_retired"
    log_event("info", "admin", event, "Admin changed a category",
              details={"category_id": category.id, "slug": category.slug, "changes": applied}, user_id=admin_id)
    return _shape(category, _usage_counts(db))


def reorder_categories(db: Session, admin_id: UUID, kind: str, ids: List[UUID]) -> List[dict]:
    category_type = CategoryType(kind)
    categories = {c.id: c for c in db.query(Category).filter(Category.type == category_type)}
    if len(ids) != len(set(ids)) or set(ids) != set(categories):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Send every {kind} category exactly once, in the new order")
    for position, category_id in enumerate(ids):
        categories[category_id].sort_order = position
    db.commit()
    log_event("info", "admin", "admin.categories_reordered", f"Admin reordered {kind} categories",
              details={"type": kind, "order": [categories[i].slug for i in ids]}, user_id=admin_id)
    return list_categories(db)


def delete_category(db: Session, admin_id: UUID, category_id: UUID) -> None:
    category = _get(db, category_id)
    in_use = _usage_counts(db).get(category.id, 0)
    if in_use:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"{in_use} listing{'s' if in_use != 1 else ''} use this category. Retire it instead.")
    slug = category.slug
    db.delete(category)
    db.commit()
    log_event("info", "admin", "admin.category_deleted", "Admin deleted an unused category",
              details={"slug": slug}, user_id=admin_id)
