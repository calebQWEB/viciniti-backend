"""seed categories and map existing data

Revision ID: 92a9c9948003
Revises: e3462cfeab83
Create Date: 2026-09-06 21:25:16.171980

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy import table, column, String, Boolean, Integer
from sqlalchemy.dialects.postgresql import UUID
import uuid

# revision identifiers, used by Alembic.
revision: str = '92a9c9948003'
down_revision: Union[str, Sequence[str], None] = 'e3462cfeab83'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

categories_table = table(
    "categories",
    column("id", UUID(as_uuid=True)),
    column("name", String),
    column("slug", String),
    column("type", String),
    column("icon", String),
    column("sort_order", Integer),
    column("is_active", Boolean),
)

ITEM_CATEGORIES = [
    ("Phones & Tablets", "phones-tablets", "smartphone"),
    ("Electronics & Gadgets", "electronics-gadgets", "monitor"),
    ("Fashion & Accessories", "fashion-accessories", "shirt"),
    ("Home, Furniture & Appliances", "home-furniture-appliances", "home"),
    ("Health & Beauty Products", "health-beauty-products", "sparkles"),
    ("Babies, Kids & Toys", "babies-kids-toys", "baby"),
    ("Vehicles & Parts", "vehicles-parts", "car"),
    ("Books, Sports & Hobbies", "books-sports-hobbies", "book-open"),
    ("Food & Agriculture", "food-agriculture", "wheat"),
    ("Other", "other-items", "package"),
]

SERVICE_CATEGORIES = [
    ("Home Repairs", "home-repairs", "wrench"),
    ("Cleaning Services", "cleaning-services", "spray-can"),
    ("Beauty & Wellness", "beauty-wellness", "sparkles"),
    ("Tutoring & Education", "tutoring-education", "book-open"),
    ("Event Services", "event-services", "camera"),
    ("Tech Support & Device Repair", "tech-support-device-repair", "smartphone"),
    ("Web, Software & Design", "web-software-design", "code"),
    ("Automotive Services", "automotive-services", "car"),
    ("Fitness & Personal Training", "fitness-personal-training", "dumbbell"),
    ("Fashion & Tailoring", "fashion-tailoring", "shirt"),
    ("Errands & Delivery", "errands-delivery", "truck"),
    ("Other", "other-services", "package"),
]

_item_ids = {}
_service_ids = {}


def upgrade() -> None:
    conn = op.get_bind()

    rows = []
    for idx, (name, slug, icon) in enumerate(ITEM_CATEGORIES):
        cat_id = uuid.uuid4()
        _item_ids[name] = cat_id
        rows.append({
            "id": cat_id, "name": name, "slug": slug, "type": "item",
            "icon": icon, "sort_order": idx, "is_active": True,
        })
    op.bulk_insert(categories_table, rows)

    rows = []
    for idx, (name, slug, icon) in enumerate(SERVICE_CATEGORIES):
        cat_id = uuid.uuid4()
        _service_ids[name] = cat_id
        rows.append({
            "id": cat_id, "name": name, "slug": slug, "type": "service",
            "icon": icon, "sort_order": idx, "is_active": True,
        })
    op.bulk_insert(categories_table, rows)

    listing_mapping = {
        "Electronics": _item_ids["Electronics & Gadgets"],
        "Other": _item_ids["Other"],
    }
    for old_value, new_id in listing_mapping.items():
        conn.execute(
            sa.text("UPDATE listings SET category_id = :cid WHERE category = :old"),
            {"cid": str(new_id), "old": old_value}
        )

    service_mapping = {
        "Photography": _service_ids["Event Services"],
        "Plumbing": _service_ids["Home Repairs"],
        "Cleaning": _service_ids["Cleaning Services"],
    }
    for old_value, new_id in service_mapping.items():
        conn.execute(
            sa.text("UPDATE services SET category_id = :cid WHERE category = :old"),
            {"cid": str(new_id), "old": old_value}
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE listings SET category_id = NULL"))
    conn.execute(sa.text("UPDATE services SET category_id = NULL"))
    conn.execute(sa.text("DELETE FROM categories"))