from huginn_muninn_api.schemas.chat import ChatRequest, ChatResponse
from huginn_muninn_api.schemas.memory import MemoryRecord


class HuginnEngine:
    personality = "professional, analytical, calm, efficient, security-focused"

    def respond(self, request: ChatRequest, memory: list[MemoryRecord]) -> ChatResponse:
        memory_context = [item.content for item in memory]
        intent = self._classify_intent(request.message)
        response = self._draft_response(request.message, intent, memory_context)

        return ChatResponse(
            response=response,
            intent=intent,
            used_memory=len(memory_context) > 0,
            memory_context=memory_context,
        )

    def _classify_intent(self, message: str) -> str:
        lowered = message.lower()
        if "log" in lowered or "ioc" in lowered or "threat" in lowered:
            return "cybersecurity"
        if "remember" in lowered or "recall" in lowered or "ask muninn" in lowered:
            return "memory"
        if "research" in lowered or "find" in lowered:
            return "research"
        if "plan" in lowered or "task" in lowered:
            return "planning"
        return "conversation"

    def _draft_response(self, message: str, intent: str, memory_context: list[str]) -> str:
        if intent == "cybersecurity":
            return (
                "Huginn is ready for defensive security analysis. Provide logs, alerts, "
                "IOCs, or incident context and I will summarize findings, map likely "
                "techniques, and recommend next actions."
            )

        if intent == "memory":
            if memory_context:
                return "Muninn found relevant memory and attached it to this response."
            return "Muninn has no matching memory yet."

        return (
            "Huginn received the request and is operating in assistive mode. "
            f"Detected intent: {intent}. Original request: {message}"
        )
