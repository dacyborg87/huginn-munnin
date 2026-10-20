import asyncio
import logging

import pytest

from core.event_bus import EventBus, EventSubmissionUnavailable
from core.events import EventType


class Store:
    def __init__(self):
        self.events = []
        self.failure = None

    async def write(self, event):
        if self.failure:
            raise self.failure
        self.events.append(event)


def bus_for(store=None, **kwargs):
    return EventBus(
        store or Store(),
        processing_timeout=kwargs.get("processing_timeout", 0.2),
        drain_timeout=0.02,
        cancellation_timeout=0.02,
    )


def assert_accounted(bus):
    h = bus.health()
    c = h["counts"]
    assert (
        c["submitted"]
        == sum(c[k] for k in ("succeeded", "failed", "timed_out", "cancelled", "abandoned"))
        + h["active"]
        + h["queued"]
    )
    assert bus._queue._unfinished_tasks == h["active"] + h["queued"]


def test_normal_lifecycle_and_repeated_shutdown():
    async def run():
        store = Store()
        bus = bus_for(store)
        assert bus.health()["state"] == "not_started"
        with pytest.raises(EventSubmissionUnavailable):
            await bus.emit(EventType.USER_COMMAND_RECEIVED, {})
        await bus.start()
        worker = bus._worker
        await bus.start()
        assert bus._worker is worker
        seen = []
        bus.subscribe(EventType.USER_COMMAND_RECEIVED, lambda event: seen.append(event.id))
        event_id = await bus.emit(EventType.USER_COMMAND_RECEIVED, {})
        assert (await bus.drain())["drained"]
        assert seen == [event_id] == [e.id for e in store.events]
        first = await bus.stop()
        assert first["state"] == "stopped"
        assert first == await bus.stop()
        with pytest.raises(EventSubmissionUnavailable):
            await bus.emit(EventType.USER_COMMAND_RECEIVED, {})
        assert_accounted(bus)
        await bus.start()
        await bus.stop()

    asyncio.run(run())


def test_storage_failure_recovery_and_sanitized_logging(caplog):
    async def run():
        store = Store()
        store.failure = RuntimeError("password=DO_NOT_LOG")
        bus = bus_for(store)
        seen = []
        bus.subscribe(EventType.USER_COMMAND_RECEIVED, lambda e: seen.append(e.id))
        await bus.start()
        failed_id = await bus.emit(EventType.USER_COMMAND_RECEIVED, {"token": "SECRET_PAYLOAD"})
        await bus.drain()
        assert not seen and not store.events
        assert bus.health()["available"]
        store.failure = None
        good = await bus.emit(EventType.USER_COMMAND_RECEIVED, {})
        await bus.drain()
        assert seen == [good]
        assert bus.health()["counts"]["failed"] == 1
        await bus.stop()
        assert_accounted(bus)
        assert failed_id in caplog.text and "stage=storage" in caplog.text
        assert "DO_NOT_LOG" not in caplog.text and "SECRET_PAYLOAD" not in caplog.text
        assert all(record.exc_info is None for record in caplog.records)

    with caplog.at_level(logging.INFO):
        asyncio.run(run())


def test_handler_failure_no_replay_and_subsequent_event():
    async def run():
        bus = bus_for()
        completed = []

        def first(event):
            completed.append((event.id, "first"))

        def failing(event):
            if event.payload.get("fail"):
                raise ValueError("sensitive")

        def last(event):
            completed.append((event.id, "last"))

        for handler in (first, failing, last):
            bus.subscribe(EventType.USER_COMMAND_RECEIVED, handler)
        await bus.start()
        bad = await bus.emit(EventType.USER_COMMAND_RECEIVED, {"fail": True})
        good = await bus.emit(EventType.USER_COMMAND_RECEIVED, {})
        await bus.drain()
        assert completed == [(bad, "first"), (good, "first"), (good, "last")]
        await bus.stop()
        assert_accounted(bus)

    asyncio.run(run())


def test_processing_timeout_keeps_worker_available():
    async def run():
        bus = bus_for(processing_timeout=0.005)
        entered = asyncio.Event()

        async def handler(event):
            if event.payload.get("block"):
                entered.set()
                await asyncio.Event().wait()

        bus.subscribe(EventType.USER_COMMAND_RECEIVED, handler)
        await bus.start()
        await bus.emit(EventType.USER_COMMAND_RECEIVED, {"block": True})
        await asyncio.wait_for(entered.wait(), 0.5)
        await bus.emit(EventType.USER_COMMAND_RECEIVED, {})
        await asyncio.wait_for(bus._queue.join(), 0.5)
        assert bus.health()["counts"]["timed_out"] == 1
        assert bus.health()["counts"]["succeeded"] == 1
        await bus.stop()
        assert_accounted(bus)

    asyncio.run(run())


@pytest.mark.parametrize("external_cancel", [False, True])
def test_unexpected_worker_exit_detected(external_cancel):
    class Fatal(BaseException):
        pass

    async def run():
        bus = bus_for()
        entered = asyncio.Event()

        async def handler(event):
            entered.set()
            if external_cancel:
                await asyncio.Event().wait()
            raise Fatal("do not expose")

        bus.subscribe(EventType.USER_COMMAND_RECEIVED, handler)
        await bus.start()
        await bus.emit(EventType.USER_COMMAND_RECEIVED, {})
        await bus.emit(EventType.USER_COMMAND_RECEIVED, {})
        await asyncio.wait_for(entered.wait(), 0.5)
        if external_cancel:
            bus._worker.cancel()
        await asyncio.gather(bus._worker, return_exceptions=True)
        assert bus.health()["state"] == "failed"
        with pytest.raises(EventSubmissionUnavailable):
            await bus.emit(EventType.USER_COMMAND_RECEIVED, {})
        with pytest.raises(EventSubmissionUnavailable):
            await bus.start()
        assert not (await bus.drain())["drained"]
        result = await asyncio.wait_for(bus.stop(), 0.5)
        assert result["counts"]["abandoned"] == 1
        assert result["counts"]["succeeded"] == 0
        assert result == await bus.stop()
        assert_accounted(bus)

    asyncio.run(run())


def test_shutdown_rejects_emissions_and_accounts_pending():
    async def run():
        bus = bus_for(processing_timeout=1)
        entered = asyncio.Event()

        async def handler(event):
            entered.set()
            await asyncio.Event().wait()

        bus.subscribe(EventType.USER_COMMAND_RECEIVED, handler)
        await bus.start()
        await bus.emit(EventType.USER_COMMAND_RECEIVED, {})
        await bus.emit(EventType.USER_COMMAND_RECEIVED, {})
        await entered.wait()
        stopped = asyncio.create_task(bus.stop())
        while bus.health()["state"] == "running":
            await asyncio.sleep(0)
        with pytest.raises(EventSubmissionUnavailable):
            await bus.emit(EventType.USER_COMMAND_RECEIVED, {})
        result = await asyncio.wait_for(stopped, 0.5)
        assert result["counts"]["cancelled"] == 1
        assert result["counts"]["abandoned"] == 1
        assert result["counts"]["succeeded"] == 0
        assert_accounted(bus)

    asyncio.run(run())


def test_cancellation_resistant_handler_reported_as_active():
    async def run():
        bus = bus_for(processing_timeout=1)
        entered, release = asyncio.Event(), asyncio.Event()

        async def handler(event):
            entered.set()
            try:
                await release.wait()
            except asyncio.CancelledError:
                await release.wait()

        bus.subscribe(EventType.USER_COMMAND_RECEIVED, handler)
        await bus.start()
        await bus.emit(EventType.USER_COMMAND_RECEIVED, {})
        await entered.wait()
        try:
            report = await asyncio.wait_for(bus.stop(), 0.5)
            assert report["state"] == "failed" and report["active"] == 1
            assert report["counts"]["succeeded"] == 0
            assert_accounted(bus)
        finally:
            release.set()
            await asyncio.gather(bus._worker, return_exceptions=True)
        assert bus.health()["counts"]["cancelled"] == 1
        assert_accounted(bus)

    asyncio.run(run())


def test_graceful_shutdown_drains_existing_work():
    async def run():
        bus = bus_for()
        entered, release = asyncio.Event(), asyncio.Event()

        async def handler(event):
            entered.set()
            await release.wait()

        bus.subscribe(EventType.USER_COMMAND_RECEIVED, handler)
        await bus.start()
        await bus.emit(EventType.USER_COMMAND_RECEIVED, {})
        await entered.wait()
        stopping = asyncio.create_task(bus.stop())
        while bus.health()["state"] == "running":
            await asyncio.sleep(0)
        release.set()
        result = await asyncio.wait_for(stopping, 0.5)
        assert result["counts"]["succeeded"] == 1
        assert result["counts"]["cancelled"] == 0
        assert_accounted(bus)

    asyncio.run(run())


def test_stop_cancellation_still_cleans_up():
    async def run():
        bus = bus_for(processing_timeout=1)
        entered = asyncio.Event()

        async def handler(event):
            entered.set()
            await asyncio.Event().wait()

        bus.subscribe(EventType.USER_COMMAND_RECEIVED, handler)
        await bus.start()
        await bus.emit(EventType.USER_COMMAND_RECEIVED, {})
        await entered.wait()
        stopping = asyncio.create_task(bus.stop())
        while bus.health()["state"] == "running":
            await asyncio.sleep(0)
        stopping.cancel()
        with pytest.raises(asyncio.CancelledError):
            await stopping
        assert not bus.health()["worker_alive"]
        assert_accounted(bus)

    asyncio.run(run())


@pytest.mark.parametrize("value", [0, -1, float("inf"), float("nan")])
def test_invalid_budgets_rejected(value):
    with pytest.raises(ValueError):
        EventBus(processing_timeout=value)
