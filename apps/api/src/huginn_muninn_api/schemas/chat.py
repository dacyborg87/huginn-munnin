from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    namespace: str = "default"
    voice_invocation: str | None = None


class ChatResponse(BaseModel):
    response: str
    intent: str
    used_memory: bool
    memory_context: list[str] = Field(default_factory=list)


class ChatAcceptedResponse(BaseModel):
    status: str
    event_id: str
