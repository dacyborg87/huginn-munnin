import asyncio
import inspect
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from threading import Lock
from typing import Any
from uuid import uuid4


class EventType(StrEnum):
    USER_COMMAND_RECEIVED = "USER_COMMAND_RECEIVED"
    CONTEXT_SIGNATURE_CREATED = "CONTEXT_SIGNATURE_CREATED"
    PATTERN_MATCH_LOOKUP = "PATTERN_MATCH_LOOKUP"
    AI_CONTEXT_ENRICHED = "AI_CONTEXT_ENRICHED"
    AI_THINKING_STARTED = "AI_THINKING_STARTED"
    AI_DECISION_MADE = "AI_DECISION_MADE"
    AI_PLAN_CREATED = "AI_PLAN_CREATED"
    AI_TASK_EXECUTING = "AI_TASK_EXECUTING"
    AI_TASK_COMPLETED = "AI_TASK_COMPLETED"
    AI_OUTCOME_RECORDED = "AI_OUTCOME_RECORDED"
    AI_PATTERN_RECORDED = "AI_PATTERN_RECORDED"
    MEMORY_WRITTEN = "MEMORY_WRITTEN"
    AGENT_STATUS_UPDATED = "AGENT_STATUS_UPDATED"


@dataclass(frozen=True)
class Event:
    event_type: EventType
    payload: dict[str, Any]
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


EventHandler = Callable[[Event], None | Awaitable[None]]


class SystemLogStore:
    """In-memory fallback for the future Postgres system_logs table."""

    def __init__(self) -> None:
        self._logs: list[Event] = []
        self._lock = Lock()

    async def write(self, event: Event) -> None:
        with self._lock:
            self._logs.append(event)

    async def list(self, limit: int = 100) -> list[Event]:
        with self._lock:
            return list(self._logs[-limit:])

    async def clear(self) -> None:
        with self._lock:
            self._logs.clear()


class EventBus:
    def __init__(self, log_store: SystemLogStore | None = None) -> None:
        self._queue: asyncio.Queue[Event] | None = None
        self._subscribers: dict[EventType, list[EventHandler]] = defaultdict(list)
        self._worker: asyncio.Task[None] | None = None
        self._running = False
        self.logs = log_store or SystemLogStore()

    def subscribe(self, event_type: EventType | str, handler: EventHandler) -> None:
        normalized = EventType(event_type)
        if handler not in self._subscribers[normalized]:
            self._subscribers[normalized].append(handler)

    async def emit(self, event_type: EventType | str, payload: dict[str, Any]) -> str:
        event = Event(event_type=EventType(event_type), payload=payload)
        if self._queue is None:
            self._queue = asyncio.Queue()
        await self._queue.put(event)
        return event.id

    async def start(self) -> None:
        if self._running:
            return
        self._queue = asyncio.Queue()
        self._running = True
        self._worker = asyncio.create_task(self._process_queue())

    async def stop(self) -> None:
        if not self._running:
            return
        if self._queue is not None:
            await self._queue.join()
        self._running = False
        if self._worker is not None:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass
            self._worker = None
        self._queue = None

    async def drain(self) -> None:
        if self._queue is not None:
            await self._queue.join()

    async def list_logs(self, limit: int = 100) -> list[Event]:
        return await self.logs.list(limit)

    async def _process_queue(self) -> None:
        while self._running:
            if self._queue is None:
                return
            event = await self._queue.get()
            try:
                await self.logs.write(event)
                await self._dispatch(event)
            finally:
                self._queue.task_done()

    async def _dispatch(self, event: Event) -> None:
        for handler in list(self._subscribers[event.event_type]):
            result = handler(event)
            if inspect.isawaitable(result):
                await result
