from pydantic import BaseModel, Field
from typing import Any, Dict, List, Literal, Optional
from datetime import datetime
from uuid import UUID

LogStatus = Literal["open", "resolved", "all"]


# A user attached to a log entry (who triggered it, or who resolved it)
class LogUser(BaseModel):
    id: UUID
    name: str
    email: str

    class Config:
        from_attributes = True


# One row in the admin list: no traceback or full details, so pages stay light
class LogListItem(BaseModel):
    id: UUID
    created_at: datetime
    level: str
    category: str
    event: str
    message: str
    user: Optional[LogUser] = None
    request_method: Optional[str] = None
    request_path: Optional[str] = None
    status_code: Optional[int] = None
    error_ref: Optional[str] = None
    alert_sent: bool = False
    resolved_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# The full entry, for the detail view
class LogDetail(LogListItem):
    details: Optional[Dict[str, Any]] = None
    traceback: Optional[str] = None
    resolver: Optional[LogUser] = None
    resolution_note: Optional[str] = None


class PaginatedLogs(BaseModel):
    items: List[LogListItem]
    total: int
    page: int
    limit: int
    total_pages: int


class LevelCounts(BaseModel):
    info: int = 0
    warning: int = 0
    error: int = 0
    critical: int = 0


# A problem that keeps happening, grouped by event
class RecurringProblem(BaseModel):
    event: str
    level: str
    count: int
    last_seen: datetime


class LogSummary(BaseModel):
    # Unresolved warnings, errors and critical entries (info is never "open")
    open: LevelCounts
    last_24h: LevelCounts
    last_7d: LevelCounts
    top_problems: List[RecurringProblem]


class ResolveRequest(BaseModel):
    note: Optional[str] = Field(default=None, max_length=2000)


# Bulk resolve takes either explicit ids or every open entry for one event
class BulkResolveRequest(BaseModel):
    ids: Optional[List[UUID]] = Field(default=None, max_length=500)
    event: Optional[str] = None
    note: Optional[str] = Field(default=None, max_length=2000)


class BulkResolveResponse(BaseModel):
    resolved: int
