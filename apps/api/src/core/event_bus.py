import asyncio
import inspect
import logging
import math
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

from core.events import Event, EventType
from core.stores.system_log_store import InMemorySystemLogStore, SystemLogStore

EventHandler = Callable[[Event], None | Awaitable[None]]
LOGGER = logging.getLogger(__name__)


class EventSubmissionUnavailable(RuntimeError):
    """The best-effort worker cannot currently accept an event."""


class EventBus:
    def __init__(
        self,
        log_store: SystemLogStore | None = None,
        *,
        processing_timeout: float = 5.0,
        drain_timeout: float = 5.0,
        cancellation_timeout: float = 1.0,
    ) -> None:
        for budget in (processing_timeout, drain_timeout, cancellation_timeout):
            if not math.isfinite(budget) or budget <= 0:
                raise ValueError("Worker time budgets must be positive and finite")
        self.processing_timeout = processing_timeout
        self.drain_timeout = drain_timeout
        self.cancellation_timeout = cancellation_timeout
        self._queue: asyncio.Queue[Event] | None = None
        self._subscribers: dict[EventType, list[EventHandler]] = defaultdict(list)
        self._worker: asyncio.Task[None] | None = None
        self._state = "not_started"
        self._active = 0
        self._unexpected_exit = False
        self._expected_cancel = False
        self._stop_lock = asyncio.Lock()
        self._counts = {
            "submitted": 0,
            "succeeded": 0,
            "failed": 0,
            "timed_out": 0,
            "cancelled": 0,
            "abandoned": 0,
        }
        self.logs = log_store or InMemorySystemLogStore()

    def bind_log_store(self, store: SystemLogStore) -> None:
        """Swap the backing store (used at startup to switch memory -> postgres)."""
        self.logs = store

    def subscribe(self, event_type: EventType | str, handler: EventHandler) -> None:
        normalized = EventType(event_type)
        if handler not in self._subscribers[normalized]:
            self._subscribers[normalized].append(handler)

    async def emit(self, event_type: EventType | str, payload: dict[str, Any]) -> str:
        self.ensure_available()
        event = Event(event_type=EventType(event_type), payload=payload)
        # No suspension between admission and enqueueing on this event loop.
        self._queue.put_nowait(event)
        self._counts["submitted"] += 1
        return event.id

    def ensure_available(self) -> None:
        if not self.health()["available"]:
            raise EventSubmissionUnavailable("Event processing is unavailable")

    def health(self) -> dict[str, Any]:
        alive = self._worker is not None and not self._worker.done()
        if self._state == "running" and not alive:
            self._state = "failed"
        return {
            "state": self._state,
            "available": self._state == "running" and alive,
            "delivery": "best_effort_in_memory",
            "queued": self._queue.qsize() if self._queue else 0,
            "active": self._active,
            "worker_alive": alive,
            "counts": dict(self._counts),
        }

    def _worker_finished(self, worker: asyncio.Task[None]) -> None:
        if not worker.cancelled():
            worker.exception()  # Retrieve without exposing the exception or its message.
        if not self._expected_cancel:
            self._unexpected_exit = True
            self._state = "failed"
            LOGGER.error("event_worker state=failed stage=worker_exit counts=%s", self._counts)

    async def start(self) -> None:
        if self.health()["available"]:
            return
        if (
            self._state in {"closing", "failed"}
            or self._active
            or (self._queue is not None and not self._queue.empty())
            or (self._worker is not None and not self._worker.done())
        ):
            raise EventSubmissionUnavailable("Worker cannot be restarted in its current state")
        self._queue = asyncio.Queue()
        self._expected_cancel = False
        self._state = "running"
        self._worker = asyncio.create_task(self._process_queue())
        self._worker.add_done_callback(self._worker_finished)

    async def stop(self) -> dict[str, Any]:
        async with self._stop_lock:
            failed = self.health()["state"] == "failed"
            if self._state in {"not_started", "stopped"}:
                self._state = "stopped"
                return self.health()
            self._state = "closing"
            try:
                await self.drain()
            finally:
                if self._worker is not None and not self._worker.done():
                    self._expected_cancel = True
                    self._worker.cancel()
                    await asyncio.wait({self._worker}, timeout=self.cancellation_timeout)
                # Only queued entries are abandoned here. The worker owns accounting
                # for its active entry, even if it refuses cancellation.
                while self._queue is not None:
                    try:
                        self._queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    self._counts["abandoned"] += 1
                    self._queue.task_done()
                alive = self._worker is not None and not self._worker.done()
                self._state = "failed" if failed or alive or self._unexpected_exit else "stopped"
                LOGGER.info("event_worker shutdown=%s", self.health())
            return self.health()

    async def drain(self) -> dict[str, Any]:
        if self._queue is None:
            return {"drained": True, **self.health()}
        joined = asyncio.create_task(self._queue.join())
        try:
            tasks = {joined}
            if self._worker is not None:
                tasks.add(self._worker)
            await asyncio.wait(
                tasks, timeout=self.drain_timeout, return_when=asyncio.FIRST_COMPLETED
            )
            return {"drained": joined.done() and not joined.cancelled(), **self.health()}
        finally:
            joined.cancel()
            await asyncio.gather(joined, return_exceptions=True)

    async def list_logs(self, limit: int = 100) -> list[Event]:
        return await self.logs.list(limit)

    async def _process_queue(self) -> None:
        while self._state in {"running", "closing"}:
            if self._queue is None:
                return
            event = await self._queue.get()
            self._active = 1
            stage = "storage"
            try:
                deadline = asyncio.timeout(self.processing_timeout)
                async with deadline:
                    await self.logs.write(event)
                    stage = "handler"
                    await self._dispatch(event)
                if asyncio.current_task().cancelling():
                    raise asyncio.CancelledError
                if deadline.expired():
                    raise TimeoutError
                self._counts["succeeded"] += 1
            except asyncio.CancelledError:
                self._record_failure(event, stage, "cancelled")
                raise
            except TimeoutError:
                self._record_failure(event, stage, "timed_out")
            except Exception:  # noqa: BLE001 - contain event failures without logging secrets
                self._record_failure(event, stage, "failed")
            except BaseException:
                self._record_failure(event, stage, "failed")
                raise
            finally:
                self._active = 0
                self._queue.task_done()

    def _record_failure(self, event: Event, stage: str, result: str) -> None:
        self._counts[result] += 1
        LOGGER.warning(
            "event_worker id=%s type=%s stage=%s state=%s result=%s counts=%s",
            event.id,
            event.event_type.value,
            stage,
            self._state,
            result,
            self._counts,
        )

    async def _dispatch(self, event: Event) -> None:
        for handler in list(self._subscribers[event.event_type]):
            result = handler(event)
            if inspect.isawaitable(result):
                await result
