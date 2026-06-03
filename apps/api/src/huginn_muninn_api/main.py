from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.event_bus import EventBus
from huginn_muninn_api.core.config import Settings
from huginn_muninn_api.core.orchestrator import Orchestrator
from huginn_muninn_api.schemas.chat import ChatAcceptedResponse, ChatRequest
from huginn_muninn_api.schemas.events import EventLogEntry
from huginn_muninn_api.schemas.memory import MemoryRecord, MemorySearchRequest
from huginn_muninn_api.schemas.security import SecurityAnalysisRequest, SecurityAnalysisResponse

settings = Settings()
event_bus = EventBus()
orchestrator = Orchestrator(event_bus)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await event_bus.start()
    yield
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
