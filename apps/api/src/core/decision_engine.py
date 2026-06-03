import re
from dataclasses import dataclass

from huginn_muninn_api.schemas.memory import MemoryRecord


@dataclass(frozen=True)
class DecisionResult:
    scores: dict[str, float]
    base_scores: dict[str, float]
    learned_weights: dict[str, float]
    pattern_influence: dict[str, float]
    matched_patterns: list[dict]
    reasoning: str
    intent: str
    memory_relevance: float
    task_complexity: float


class DecisionEngine:
    security_terms = {
        "alert",
        "ioc",
        "log",
        "logs",
        "malware",
        "mitre",
        "suricata",
        "threat",
        "wazuh",
    }
    memory_terms = {"again", "continue", "previous", "prior", "recall", "remember", "yesterday"}
    planning_terms = {"build", "create", "design", "implement", "plan", "report", "workflow"}

    def evaluate(
        self,
        message: str,
        relevant_memory: list[MemoryRecord],
        learned_weights: dict[str, float] | None = None,
        pattern_influence: dict[str, float] | None = None,
        matched_patterns: list[dict] | None = None,
    ) -> DecisionResult:
        tokens = self._tokens(message)
        intent = self._intent(tokens)
        memory_relevance = self._memory_relevance(tokens, relevant_memory)
        task_complexity = self._task_complexity(tokens, message)
        learned_weights = learned_weights or {}
        pattern_influence = pattern_influence or {}
        matched_patterns = matched_patterns or []

        scores = {
            "PLANNING": 0.34 + task_complexity * 0.31,
            "MEMORY_LOOKUP": 0.18 + memory_relevance * 0.54,
            "TOOL_USE": 0.16,
        }

        if intent == "cybersecurity":
            scores["TOOL_USE"] += 0.43
            scores["PLANNING"] += 0.08
        if tokens & self.memory_terms:
            scores["MEMORY_LOOKUP"] += 0.18
        if tokens & self.planning_terms:
            scores["PLANNING"] += 0.14

        base_scores = self._normalize(scores)
        for state, weight in learned_weights.items():
            if state in scores:
                scores[state] = max(0.01, scores[state] + weight)
        for state, influence in pattern_influence.items():
            if state in scores:
                scores[state] = max(0.01, scores[state] + influence)

        normalized = self._normalize(scores)
        selected_state = max(normalized, key=normalized.get)
        reasoning = self._reasoning(
            selected_state,
            intent,
            memory_relevance,
            task_complexity,
            learned_weights,
            pattern_influence,
            matched_patterns,
        )

        return DecisionResult(
            scores=normalized,
            base_scores=base_scores,
            learned_weights={state: round(learned_weights.get(state, 0.0), 3) for state in scores},
            pattern_influence={
                state: round(pattern_influence.get(state, 0.0), 3) for state in scores
            },
            matched_patterns=matched_patterns,
            reasoning=reasoning,
            intent=intent,
            memory_relevance=memory_relevance,
            task_complexity=task_complexity,
        )

    def _intent(self, tokens: set[str]) -> str:
        if tokens & self.security_terms:
            return "cybersecurity"
        if tokens & self.memory_terms:
            return "memory"
        if tokens & self.planning_terms:
            return "planning"
        return "conversation"

    def _memory_relevance(self, tokens: set[str], memory: list[MemoryRecord]) -> float:
        if not memory:
            return 0.0

        best_overlap = 0.0
        for record in memory:
            memory_tokens = self._tokens(record.content)
            if not memory_tokens:
                continue
            overlap = len(tokens & memory_tokens) / max(len(tokens), 1)
            tag_overlap = len(tokens & set(record.tags)) / max(len(tokens), 1)
            best_overlap = max(best_overlap, min(1.0, overlap + tag_overlap))
        return best_overlap

    def _task_complexity(self, tokens: set[str], message: str) -> float:
        complexity = 0.15
        if len(message) > 90:
            complexity += 0.25
        if len(tokens & self.planning_terms) >= 1:
            complexity += 0.35
        if len(tokens) > 12:
            complexity += 0.15
        return min(1.0, complexity)

    def _reasoning(
        self,
        selected_state: str,
        intent: str,
        memory_relevance: float,
        task_complexity: float,
        learned_weights: dict[str, float],
        pattern_influence: dict[str, float],
        matched_patterns: list[dict],
    ) -> str:
        learned_weight = learned_weights.get(selected_state, 0.0)
        pattern_weight = pattern_influence.get(selected_state, 0.0)
        learning_context = (
            f" Learned outcome weight for this path is {learned_weight:+.2f}."
            if learned_weight
            else " No strong outcome bias exists yet."
        )
        pattern_context = (
            f" Reasoning patterns add {pattern_weight:+.2f} from "
            f"{len(matched_patterns)} similar context(s)."
            if matched_patterns
            else " No matching reasoning pattern exists yet."
        )
        if selected_state == "MEMORY_LOOKUP":
            return (
                "Muninn memory had enough overlap with the command to route through contextual "
                f"retrieval before execution.{learning_context}{pattern_context}"
            )
        if selected_state == "TOOL_USE":
            return (
                "Security or operational indicators were detected, so Huginn selected a tool-use "
                f"execution branch.{learning_context}{pattern_context}"
            )
        return (
            "The command appears to require structured reasoning. Huginn selected planning based "
            f"on intent={intent}, memory_relevance={memory_relevance:.2f}, "
            f"task_complexity={task_complexity:.2f}.{learning_context}{pattern_context}"
        )

    def _normalize(self, scores: dict[str, float]) -> dict[str, float]:
        total = sum(scores.values())
        return {state: round(score / total, 3) for state, score in scores.items()}

    def _tokens(self, text: str) -> set[str]:
        return set(re.findall(r"[a-z0-9]+", text.lower()))
