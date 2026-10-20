import asyncio
import logging
import math
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.event_bus import EventBus, EventSubmissionUnavailable
from huginn_muninn_api.core.config import Settings
from huginn_muninn_api.core.evidence_api import EvidenceApi
from huginn_muninn_api.core.graph_intelligence_api import GraphIntelligenceApi
from huginn_muninn_api.core.guardduty_ingest_api import GuardDutyIngestApi
from huginn_muninn_api.core.live_telemetry_api import LiveTelemetryApi
from huginn_muninn_api.core.orchestrator import Orchestrator
from huginn_muninn_api.core.persistence import build_stores
from huginn_muninn_api.core.wazuh_ingest_api import WazuhIngestApi
from huginn_muninn_api.schemas.chat import ChatAcceptedResponse, ChatRequest
from huginn_muninn_api.schemas.events import EventLogEntry
from huginn_muninn_api.schemas.memory import MemoryRecord, MemorySearchRequest
from huginn_muninn_api.schemas.security import SecurityAnalysisRequest, SecurityAnalysisResponse

settings = Settings()
LOGGER = logging.getLogger(__name__)


def _budget(name: str, default: float) -> float:
    value = float(os.environ.get(name, default))
    if not math.isfinite(value) or value <= 0:
        raise ValueError("Lifecycle time budgets must be positive and finite")
    return value


event_bus = EventBus(
    processing_timeout=_budget("EVENT_PROCESSING_TIMEOUT_SECONDS", 5.0),
    drain_timeout=_budget("EVENT_DRAIN_TIMEOUT_SECONDS", 5.0),
    cancellation_timeout=_budget("EVENT_CANCELLATION_TIMEOUT_SECONDS", 1.0),
)
POOL_CLOSE_TIMEOUT = _budget("DATABASE_POOL_CLOSE_TIMEOUT_SECONDS", 5.0)
orchestrator = Orchestrator(event_bus)
repository_root = Path(__file__).resolve().parents[4]
graph_intelligence = GraphIntelligenceApi(repository_root)
evidence_api = EvidenceApi(repository_root)
live_telemetry_api = LiveTelemetryApi(repository_root)
wazuh_ingest_api = WazuhIngestApi(repository_root)
guardduty_ingest_api = GuardDutyIngestApi(repository_root)

_store_pool = None


async def _close_pool(pool, timeout: float) -> None:
    closing = asyncio.create_task(pool.close())
    try:
        done, _ = await asyncio.wait({closing}, timeout=timeout)
        if not done:
            LOGGER.warning("database_pool stage=close result=timeout")
            return
        await closing
    except Exception:  # noqa: BLE001 - cleanup must not expose database error details
        LOGGER.warning("database_pool stage=close result=failed")
    finally:
        if not closing.done() or closing.cancelled() or closing.exception() is not None:
            closing.cancel()
            pool.terminate()
            # Retrieve eventual failures without waiting indefinitely for cancellation.
            closing.add_done_callback(lambda task: None if task.cancelled() else task.exception())


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    global _store_pool

    # Backend selection happens in exactly one place: settings.persistence_backend
    # decides in-memory (default) vs Postgres. See huginn_muninn_api.core.persistence.
    stores = await build_stores(settings)
    _store_pool = stores.pool
    try:
        event_bus.bind_log_store(stores.system_log_store)
        orchestrator.muninn.bind_store(stores.memory_store)
        orchestrator.outcome_tracker.bind_store(stores.outcome_store)
        orchestrator.reasoning_patterns.bind_store(stores.pattern_store)
        await orchestrator.hydrate()
        await event_bus.start()
        await live_telemetry_api.start_polling()
        yield
    finally:
        try:
            await event_bus.stop()
        finally:
            try:
                await live_telemetry_api.stop_polling()
            finally:
                if _store_pool is not None:
                    await _close_pool(_store_pool, POOL_CLOSE_TIMEOUT)
                    _store_pool = None


app = FastAPI(
    title="HUGINN // MUNINN API",
    description="Defensive intelligence dashboard backend — security telemetry ingestion, graph intelligence, and evidence analysis.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(EventSubmissionUnavailable)
async def event_submission_unavailable(_: Request, __: EventSubmissionUnavailable) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": "Event processing is unavailable"})


@app.get("/health")
async def health(response: Response) -> dict[str, Any]:
    worker = event_bus.health()
    response.status_code = 200 if worker["available"] else 503
    return {
        "status": "ok" if worker["available"] else "degraded",
        "system": "huginn-muninn",
        "event_worker": worker,
        "database_readiness": "not_checked",
    }


@app.post("/chat", response_model=ChatAcceptedResponse)
async def chat(request: ChatRequest) -> ChatAcceptedResponse:
    event_bus.ensure_available()
    return await orchestrator.chat(request)


@app.post("/memory", response_model=MemoryRecord)
async def remember(record: MemoryRecord) -> MemoryRecord:
    event_bus.ensure_available()
    return await orchestrator.remember(record)


@app.post("/memory/search", response_model=list[MemoryRecord])
async def search_memory(request: MemorySearchRequest) -> list[MemoryRecord]:
    return await orchestrator.search_memory(request)


@app.post("/security/analyze", response_model=SecurityAnalysisResponse)
def analyze_security(request: SecurityAnalysisRequest) -> SecurityAnalysisResponse:
    return orchestrator.analyze_security(request)


@app.post("/ingest/wazuh")
def ingest_wazuh(payload: dict[str, Any] | list[Any]) -> dict[str, Any]:
    try:
        return wazuh_ingest_api.ingest(payload)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@app.post("/ingest/guardduty")
def ingest_guardduty(payload: dict[str, Any] | list[Any]) -> dict[str, Any]:
    try:
        return guardduty_ingest_api.ingest(payload)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@app.get("/events", response_model=list[EventLogEntry])
async def list_events(limit: int = 100) -> list[EventLogEntry]:
    events = await event_bus.list_logs(limit)
    return [
        EventLogEntry(
            id=event.id,
            event_type=event.event_type.value,
            payload=event.payload,
            created_at=event.created_at,
        )
        for event in events
    ]


@app.get("/graph/summary")
def graph_summary() -> dict:
    return graph_intelligence.summary()


@app.get("/graph/related/{entity_id}")
def graph_related(entity_id: str) -> dict:
    return graph_intelligence.related(entity_id)


@app.get("/graph/weaknesses/{entity_id}")
def graph_weaknesses(entity_id: str) -> dict:
    return graph_intelligence.weaknesses(entity_id)


@app.get("/graph/recommendations/{technique_id}")
def graph_recommendations(technique_id: str) -> dict:
    return graph_intelligence.recommendations(technique_id)


@app.get("/graph/similar-incidents/{event_id}")
def graph_similar_incidents(event_id: str) -> dict:
    return graph_intelligence.similar_incidents(event_id)


@app.get("/evidence/summary")
def evidence_summary() -> dict:
    return evidence_api.summary()


@app.get("/evidence/finding/{finding_id}")
def evidence_by_finding(finding_id: str) -> dict:
    return evidence_api.finding(finding_id)


@app.get("/evidence/mitre/{technique_id}")
def evidence_by_mitre(technique_id: str) -> dict:
    return evidence_api.mitre(technique_id)


@app.get("/evidence/weakness/{weakness_id}")
def evidence_by_weakness(weakness_id: str) -> dict:
    return evidence_api.weakness(weakness_id)


@app.get("/evidence/recommendation/{recommendation_id}")
def evidence_by_recommendation(recommendation_id: str) -> dict:
    return evidence_api.recommendation(recommendation_id)


@app.get("/evidence/confidence/{level}")
def evidence_by_confidence(level: str) -> dict:
    return evidence_api.confidence(level)


@app.get("/dashboard/summary")
def dashboard_summary() -> dict:
    return live_telemetry_api.summary()


@app.get("/dashboard/events")
def dashboard_events() -> dict:
    return live_telemetry_api.events()


@app.get("/dashboard/rules")
def dashboard_rules() -> dict:
    return live_telemetry_api.rules()


@app.get("/dashboard/agents")
def dashboard_agents() -> dict:
    return live_telemetry_api.agents()


@app.get("/dashboard/evidence")
def dashboard_evidence() -> dict:
    return live_telemetry_api.evidence()


@app.get("/dashboard/last-updated")
def dashboard_last_updated() -> dict:
    return live_telemetry_api.last_updated()
