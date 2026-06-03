from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class MemoryRecord(BaseModel):
    id: str | None = None
    namespace: str = "default"
    content: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class MemorySearchRequest(BaseModel):
    query: str = Field(min_length=1)
    namespace: str | None = "default"
    limit: int = Field(default=5, ge=1, le=25)
