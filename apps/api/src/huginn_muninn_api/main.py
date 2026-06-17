from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from core.event_bus import EventBus
from huginn_muninn_api.core.config import Settings
from huginn_muninn_api.core.evidence_api import EvidenceApi
from huginn_muninn_api.core.graph_intelligence_api import GraphIntelligenceApi
from huginn_muninn_api.core.live_telemetry_api import LiveTelemetryApi
from huginn_muninn_api.core.orchestrator import Orchestrator
from huginn_muninn_api.core.wazuh_ingest_api import WazuhIngestApi
from huginn_muninn_api.schemas.chat import ChatAcceptedResponse, ChatRequest
from huginn_muninn_api.schemas.events import EventLogEntry
from huginn_muninn_api.schemas.memory import MemoryRecord, MemorySearchRequest
from huginn_muninn_api.schemas.security import SecurityAnalysisRequest, SecurityAnalysisResponse

settings = Settings()
event_bus = EventBus()
orchestrator = Orchestrator(event_bus)
repository_root = Path(__file__).resolve().parents[4]
graph_intelligence = GraphIntelligenceApi(repository_root)
evidence_api = EvidenceApi(repository_root)
live_telemetry_api = LiveTelemetryApi(repository_root)
wazuh_ingest_api = WazuhIngestApi(repository_root)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await event_bus.start()
    await live_telemetry_api.start_polling()
    try:
        yield
    finally:
        await live_telemetry_api.stop_polling()
        await event_bus.stop()

app = FastAPI(
    title="HUGINN // MUNINN API",
    description="Thought and memory engine backend for a modular AI command center.",
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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "system": "huginn-muninn"}


@app.post("/chat", response_model=ChatAcceptedResponse)
async def chat(request: ChatRequest) -> ChatAcceptedResponse:
    return await orchestrator.chat(request)


@app.post("/memory", response_model=MemoryRecord)
async def remember(record: MemoryRecord) -> MemoryRecord:
    return await orchestrator.remember(record)


@app.post("/memory/search", response_model=list[MemoryRecord])
def search_memory(request: MemorySearchRequest) -> list[MemoryRecord]:
    return orchestrator.search_memory(request)


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
