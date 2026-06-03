from datetime import datetime
from typing import Any

from pydantic import BaseModel


class EventLogEntry(BaseModel):
    id: str
    event_type: str
    payload: dict[str, Any]
    created_at: datetime
