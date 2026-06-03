from typing import Any

from core.decision_engine import DecisionEngine
from core.event_bus import Event, EventBus, EventType
from core.intelligence_graph import Graph, GraphContext, Node, Transition
from core.outcome_tracker import OutcomeResult, OutcomeTracker
from core.reasoning_patterns import ContextSignature, ReasoningPatternEngine
from huginn_muninn_api.huginn.engine import HuginnEngine
from huginn_muninn_api.huginn.security import CybersecurityEngine
from huginn_muninn_api.muninn.memory import MuninnMemory
from huginn_muninn_api.schemas.chat import ChatAcceptedResponse, ChatRequest
from huginn_muninn_api.schemas.memory import MemoryRecord, MemorySearchRequest
from huginn_muninn_api.schemas.security import SecurityAnalysisRequest, SecurityAnalysisResponse


class Orchestrator:
    def __init__(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus
        self.huginn = HuginnEngine()
        self.muninn = MuninnMemory()
        self.security = CybersecurityEngine()
        self.decision_engine = DecisionEngine()
        self.outcome_tracker = OutcomeTracker()
        self.reasoning_patterns = ReasoningPatternEngine()
        self.graph = self._build_graph()
        self._register_handlers()

    async def chat(self, request: ChatRequest) -> ChatAcceptedResponse:
        event_id = await self.event_bus.emit(
            EventType.USER_COMMAND_RECEIVED,
            {
                "message": request.message,
                "namespace": request.namespace,
                "voice_invocation": request.voice_invocation,
            },
        )
        return ChatAcceptedResponse(status="accepted", event_id=event_id)

    async def remember(self, record: MemoryRecord) -> MemoryRecord:
        stored = self.muninn.write(record)
        await self.event_bus.emit(
            EventType.MEMORY_WRITTEN,
            {
                "memory_id": stored.id,
                "namespace": stored.namespace,
                "tags": stored.tags,
                "source": "api",
            },
        )
        return stored

    def search_memory(self, request: MemorySearchRequest) -> list[MemoryRecord]:
        return self.muninn.search(request)

    def analyze_security(self, request: SecurityAnalysisRequest) -> SecurityAnalysisResponse:
        return self.security.analyze(request)

    def _register_handlers(self) -> None:
        self.event_bus.subscribe(EventType.USER_COMMAND_RECEIVED, self._on_user_command_received)
        self.event_bus.subscribe(EventType.AI_THINKING_STARTED, self._on_ai_thinking_started)
        self.event_bus.subscribe(EventType.AI_DECISION_MADE, self._on_ai_decision_made)
        self.event_bus.subscribe(EventType.AI_PLAN_CREATED, self._on_ai_plan_created)
        self.event_bus.subscribe(EventType.AI_TASK_EXECUTING, self._on_ai_task_executing)

    async def _on_user_command_received(self, event: Event) -> None:
        await self.event_bus.emit(
            EventType.AI_THINKING_STARTED,
            {
                "command_event_id": event.id,
                "message": event.payload["message"],
                "namespace": event.payload.get("namespace", "default"),
            },
        )

    async def _on_ai_thinking_started(self, event: Event) -> None:
        request = ChatRequest(
            message=event.payload["message"],
            namespace=event.payload.get("namespace", "default"),
        )
        relevant_memory = self.muninn.search(
            MemorySearchRequest(query=request.message, limit=3, namespace=request.namespace)
        )
        learned_weights = self._learned_weights_from_memory(request.namespace)
        baseline_decision = self.decision_engine.evaluate(
            request.message, relevant_memory, learned_weights=learned_weights
        )
        context_signature = self.reasoning_patterns.create_context_signature(
            message=request.message,
            intent=baseline_decision.intent,
            memory=relevant_memory,
            memory_relevance=baseline_decision.memory_relevance,
            system_state="THINKING",
        )
        await self.event_bus.emit(
            EventType.CONTEXT_SIGNATURE_CREATED,
            {
                "command_event_id": event.payload["command_event_id"],
                "thinking_event_id": event.id,
                "context_signature": context_signature.to_dict(),
            },
        )
        pattern_matches = self.reasoning_patterns.match_patterns(context_signature)
        pattern_match_payloads = [match.to_dict() for match in pattern_matches]
        pattern_influence = self.reasoning_patterns.influence_from_matches(pattern_matches)
        await self.event_bus.emit(
            EventType.PATTERN_MATCH_LOOKUP,
            {
                "command_event_id": event.payload["command_event_id"],
                "matched_patterns": pattern_match_payloads,
                "pattern_influence": pattern_influence,
            },
        )
        decision = self.decision_engine.evaluate(
            request.message,
            relevant_memory,
            learned_weights=learned_weights,
            pattern_influence=pattern_influence,
            matched_patterns=pattern_match_payloads,
        )
        context: GraphContext = {
            "current_state": "THINKING",
            "command_event_id": event.payload["command_event_id"],
            "thinking_event_id": event.id,
            "message": request.message,
            "namespace": request.namespace,
            "memory": relevant_memory,
            "memory_context": [record.content for record in relevant_memory],
            "decision_scores": decision.scores,
            "base_scores": decision.base_scores,
            "learned_weights": decision.learned_weights,
            "pattern_influence": decision.pattern_influence,
            "matched_patterns": decision.matched_patterns,
            "context_signature": context_signature.to_dict(),
            "reasoning": decision.reasoning,
            "intent": decision.intent,
            "memory_relevance": decision.memory_relevance,
            "task_complexity": decision.task_complexity,
        }
        selected_node = self.graph.resolve_next_state(context)
        await self.event_bus.emit(
            EventType.AI_DECISION_MADE,
            {
                "command_event_id": event.payload["command_event_id"],
                "thinking_event_id": event.id,
                "current_state": "THINKING",
                "candidate_states": list(decision.scores),
                "selected_state": selected_node.id,
                "confidence_scores": decision.scores,
                "base_scores": decision.base_scores,
                "learned_weights": decision.learned_weights,
                "pattern_influence": decision.pattern_influence,
                "matched_patterns": decision.matched_patterns,
                "context_signature": context_signature.to_dict(),
                "reasoning": decision.reasoning,
                "intent": decision.intent,
                "memory_relevance": decision.memory_relevance,
                "task_complexity": decision.task_complexity,
                "memory_context": context["memory_context"],
                "message": request.message,
                "namespace": request.namespace,
            },
        )

    async def _on_ai_decision_made(self, event: Event) -> None:
        node = self.graph.nodes[event.payload["selected_state"]]
        context = node.handler_function(
            {
                "message": event.payload["message"],
                "namespace": event.payload["namespace"],
                "intent": event.payload["intent"],
                "memory_context": event.payload["memory_context"],
                "command_event_id": event.payload["command_event_id"],
                "decision_event_id": event.id,
                "reasoning": event.payload["reasoning"],
                "confidence_scores": event.payload["confidence_scores"],
                "base_scores": event.payload["base_scores"],
                "learned_weights": event.payload["learned_weights"],
                "pattern_influence": event.payload["pattern_influence"],
                "matched_patterns": event.payload["matched_patterns"],
                "context_signature": event.payload["context_signature"],
            }
        )

        if node.id == "PLANNING":
            await self.event_bus.emit(EventType.AI_PLAN_CREATED, context)
            return

        await self.event_bus.emit(EventType.AI_TASK_EXECUTING, context)

    async def _on_ai_plan_created(self, event: Event) -> None:
        await self.event_bus.emit(
            EventType.AI_TASK_EXECUTING,
            {
                "command_event_id": event.payload["command_event_id"],
                "plan_event_id": event.id,
                "task": "record_pipeline_result",
                "intent": event.payload["intent"],
                "response": event.payload["response"],
                "namespace": event.payload["namespace"],
                "selected_state": "PLANNING",
                "decision_event_id": event.payload["decision_event_id"],
                "reasoning": event.payload["reasoning"],
                "message": event.payload["message"],
                "context_signature": event.payload["context_signature"],
                "matched_patterns": event.payload["matched_patterns"],
                "pattern_influence": event.payload["pattern_influence"],
            },
        )

    async def _on_ai_task_executing(self, event: Event) -> None:
        started_at = self.outcome_tracker.start_timer()
        result, error_logs = self._determine_outcome(event.payload)
        outcome, updated_weights = self.outcome_tracker.record(
            event_id=event.id,
            initial_state="THINKING",
            chosen_path=event.payload["selected_state"],
            result=result,
            started_at=started_at,
            error_logs=error_logs,
        )
        stored = self.muninn.write(
            MemoryRecord(
                namespace=event.payload["namespace"],
                content=f"Processed command as {event.payload['intent']}: {event.payload['response']}",
                tags=["intelligence_graph", event.payload["selected_state"].lower()],
                metadata={
                    "command_event_id": event.payload["command_event_id"],
                    "decision_event_id": event.payload["decision_event_id"],
                    "selected_state": event.payload["selected_state"],
                    "reasoning": event.payload["reasoning"],
                    "task_event_id": event.id,
                    "outcome": outcome.to_memory(),
                },
            )
        )
        outcome_memory = self.muninn.write(
            MemoryRecord(
                namespace=event.payload["namespace"],
                content=(
                    "learning_weights outcome "
                    f"{outcome.chosen_path} {outcome.result} "
                    f"performance {outcome.performance_score}"
                ),
                tags=["learning_weights", "outcome", outcome.chosen_path.lower(), outcome.result],
                metadata={
                    "outcome": outcome.to_memory(),
                    "updated_weights": updated_weights,
                },
            )
        )
        await self.event_bus.emit(
            EventType.MEMORY_WRITTEN,
            {
                "memory_id": stored.id,
                "namespace": stored.namespace,
                "tags": stored.tags,
                "source": "event_pipeline",
                "command_event_id": event.payload["command_event_id"],
                "selected_state": event.payload["selected_state"],
            },
        )
        await self.event_bus.emit(
            EventType.MEMORY_WRITTEN,
            {
                "memory_id": outcome_memory.id,
                "namespace": outcome_memory.namespace,
                "tags": outcome_memory.tags,
                "source": "outcome_tracker",
                "command_event_id": event.payload["command_event_id"],
                "selected_state": event.payload["selected_state"],
            },
        )
        await self.event_bus.emit(
            EventType.AI_TASK_COMPLETED,
            {
                "command_event_id": event.payload["command_event_id"],
                "task_event_id": event.id,
                "memory_id": stored.id,
                "intent": event.payload["intent"],
                "selected_state": event.payload["selected_state"],
            },
        )
        await self.event_bus.emit(
            EventType.AI_OUTCOME_RECORDED,
            {
                "command_event_id": event.payload["command_event_id"],
                "task_event_id": event.id,
                "selected_path": outcome.chosen_path,
                "result": outcome.result,
                "performance_score": outcome.performance_score,
                "execution_time": outcome.execution_time,
                "error_logs": outcome.error_logs,
                "updated_weights": updated_weights,
            },
        )
        context_signature = ContextSignature(**event.payload["context_signature"])
        pattern, matched_contexts = self.reasoning_patterns.record_outcome(
            signature=context_signature,
            chosen_path=event.payload["selected_state"],
            outcome=outcome,
        )
        pattern_memory = self.muninn.write(
            MemoryRecord(
                namespace=event.payload["namespace"],
                content=(
                    "reasoning_pattern "
                    f"{pattern.pattern_id} intent {context_signature.intent} "
                    f"path {event.payload['selected_state']} success {pattern.success_rate}"
                ),
                tags=["reasoning_pattern", event.payload["selected_state"].lower()],
                metadata={"pattern": pattern.to_dict()},
            )
        )
        await self.event_bus.emit(
            EventType.MEMORY_WRITTEN,
            {
                "memory_id": pattern_memory.id,
                "namespace": pattern_memory.namespace,
                "tags": pattern_memory.tags,
                "source": "reasoning_patterns",
                "command_event_id": event.payload["command_event_id"],
                "selected_state": event.payload["selected_state"],
            },
        )
        await self.event_bus.emit(
            EventType.AI_PATTERN_RECORDED,
            {
                "command_event_id": event.payload["command_event_id"],
                "pattern_id": pattern.pattern_id,
                "matched_contexts": matched_contexts,
                "success_rate": pattern.success_rate,
                "updated_distribution": pattern.preferred_path_distribution,
                "conditions": pattern.conditions,
            },
        )
        await self.event_bus.emit(
            EventType.AGENT_STATUS_UPDATED,
            {
                "agent": "huginn",
                "status": "idle",
                "command_event_id": event.payload["command_event_id"],
            },
        )

    def _build_graph(self) -> Graph:
        graph = Graph()
        graph.add_node(Node("THINKING", "analysis", self._thinking_node))
        graph.add_node(Node("PLANNING", "planning", self._planning_node))
        graph.add_node(Node("MEMORY_LOOKUP", "memory", self._memory_lookup_node))
        graph.add_node(Node("TOOL_USE", "tool_use", self._tool_use_node))

        for target in ("MEMORY_LOOKUP", "TOOL_USE", "PLANNING"):
            graph.add_transition(
                "THINKING",
                Transition(
                    condition_function=lambda context, state=target: self._state_has_top_score(
                        context, state
                    ),
                    target_node=target,
                ),
            )
        return graph

    def _state_has_top_score(self, context: GraphContext, state: str) -> bool:
        scores = context.get("decision_scores", {})
        return bool(scores) and max(scores, key=scores.get) == state

    def _thinking_node(self, context: GraphContext) -> GraphContext:
        return context

    def _planning_node(self, context: GraphContext) -> GraphContext:
        request = ChatRequest(message=context["message"], namespace=context["namespace"])
        memory_records = [
            MemoryRecord(content=content, namespace=context["namespace"])
            for content in context["memory_context"]
        ]
        response = self.huginn.respond(request, memory_records)
        return {
            **self._base_task_context(context, "PLANNING"),
            "plan": [
                "decompose_request",
                "evaluate_memory_constraints",
                "define_execution_steps",
                "record_graph_result",
            ],
            "response": response.response,
        }

    def _memory_lookup_node(self, context: GraphContext) -> GraphContext:
        memory_summary = (
            " | ".join(context["memory_context"])
            if context["memory_context"]
            else "Muninn found no matching records."
        )
        return {
            **self._base_task_context(context, "MEMORY_LOOKUP"),
            "task": "memory_context_retrieval",
            "response": f"Muninn context selected for routing: {memory_summary}",
        }

    def _tool_use_node(self, context: GraphContext) -> GraphContext:
        if context["intent"] == "cybersecurity":
            analysis = self.security.analyze(
                SecurityAnalysisRequest(content=context["message"], source="intelligence_graph")
            )
            response = f"{analysis.severity.upper()}: {analysis.summary}"
        else:
            response = "Huginn selected tool-use mode for operational execution."
        return {
            **self._base_task_context(context, "TOOL_USE"),
            "task": "tool_execution",
            "response": response,
        }

    def _base_task_context(self, context: GraphContext, selected_state: str) -> dict[str, Any]:
        return {
            "command_event_id": context["command_event_id"],
            "decision_event_id": context["decision_event_id"],
            "selected_state": selected_state,
            "intent": context["intent"],
            "namespace": context["namespace"],
            "memory_context": context["memory_context"],
            "reasoning": context["reasoning"],
            "confidence_scores": context["confidence_scores"],
            "base_scores": context["base_scores"],
            "learned_weights": context["learned_weights"],
            "pattern_influence": context["pattern_influence"],
            "matched_patterns": context["matched_patterns"],
            "context_signature": context["context_signature"],
            "message": context["message"],
        }

    def _determine_outcome(self, payload: dict[str, Any]) -> tuple[OutcomeResult, list[str]]:
        message = payload.get("message", "").lower()
        selected_state = payload["selected_state"]
        response = payload.get("response", "")

        if selected_state == "TOOL_USE" and (
            "simulate failure" in message or "force failure" in message or "tool failure" in message
        ):
            return "failure", ["Tool-use branch received a simulated failure command."]

        if selected_state == "MEMORY_LOOKUP" and "no matching records" in response.lower():
            return "partial", ["Memory lookup branch did not find enough context."]

        return "success", []

    def _learned_weights_from_memory(self, namespace: str) -> dict[str, float]:
        learned_weights = self.outcome_tracker.weights()
        learning_records = self.muninn.search(
            MemorySearchRequest(query="learning_weights outcome", namespace=namespace, limit=10)
        )

        for record in learning_records:
            weights = record.metadata.get("updated_weights")
            if isinstance(weights, dict):
                learned_weights.update(
                    {
                        str(path): float(weight)
                        for path, weight in weights.items()
                        if isinstance(weight, int | float)
                    }
                )

        self.outcome_tracker.load_weights(learned_weights)
        return learned_weights
