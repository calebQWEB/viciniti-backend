from sqlalchemy import Column, String, Boolean, Integer, Enum
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base
from datetime import datetime
import uuid
import enum

class CategoryType(enum.Enum):
    item = "item"
    service = "service"

class Category(Base):
    __tablename__ = "categories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    slug = Column(String, nullable=False, unique=True)
    type = Column(Enum(CategoryType), nullable=False)
    icon = Column(String, nullable=True)
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)