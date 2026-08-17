import asyncio
import inspect
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

from core.events import Event, EventType
from core.stores.system_log_store import InMemorySystemLogStore, SystemLogStore


EventHandler = Callable[[Event], None | Awaitable[None]]


class EventBus:
    def __init__(self, log_store: SystemLogStore | None = None) -> None:
        self._queue: asyncio.Queue[Event] | None = None
        self._subscribers: dict[EventType, list[EventHandler]] = defaultdict(list)
        self._worker: asyncio.Task[None] | None = None
        self._running = False
        self.logs = log_store or InMemorySystemLogStore()

    def bind_log_store(self, store: SystemLogStore) -> None:
        """Swap the backing store (used at startup to switch memory -> postgres)."""
        self.logs = store

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
