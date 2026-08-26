import re
from dataclasses import dataclass
from typing import Any

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
    domain_evidence: dict[str, float]


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

    # Phase B2: Security Knowledge Graph evidence. Bounded and additive —
    # see _domain_evidence() — never a hard routing override.
    action_terms = {
        "investigate",
        "analyze",
        "respond",
        "contain",
        "remediate",
        "block",
        "isolate",
        "triage",
        "hunt",
    }
    informational_terms = {"what", "explain", "describe", "define", "tell", "overview"}
    DOMAIN_EVIDENCE_CAP = 0.15
    NEUTRAL_DOMAIN_EVIDENCE_CAP = 0.05

    def evaluate(
        self,
        message: str,
        relevant_memory: list[MemoryRecord],
        learned_weights: dict[str, float] | None = None,
        pattern_influence: dict[str, float] | None = None,
        matched_patterns: list[dict] | None = None,
        intelligence_context: dict[str, Any] | None = None,
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

        domain_evidence, domain_metadata = self._domain_evidence(intelligence_context, tokens)
        for state, evidence in domain_evidence.items():
            if state in scores:
                scores[state] = max(0.01, scores[state] + evidence)

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
            domain_evidence,
            domain_metadata,
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
            domain_evidence={state: round(value, 3) for state, value in domain_evidence.items()},
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
        domain_evidence: dict[str, float],
        domain_metadata: dict[str, Any],
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
        domain_context = (
            f" Security knowledge graph evidence ({domain_metadata['query_shape']}) adds "
            f"{domain_evidence.get(selected_state, 0.0):+.2f} from "
            f"{domain_metadata['mitre_technique_count']} technique(s), "
            f"{domain_metadata['weakness_count']} weakness(es)."
            if domain_evidence
            else " No security knowledge graph evidence was available."
        )
        if selected_state == "MEMORY_LOOKUP":
            return (
                "Muninn memory had enough overlap with the command to route through contextual "
                f"retrieval before execution.{learning_context}{pattern_context}{domain_context}"
            )
        if selected_state == "TOOL_USE":
            return (
                "Security or operational indicators were detected, so Huginn selected a tool-use "
                f"execution branch.{learning_context}{pattern_context}{domain_context}"
            )
        return (
            "The command appears to require structured reasoning. Huginn selected planning based "
            f"on intent={intent}, memory_relevance={memory_relevance:.2f}, "
            f"task_complexity={task_complexity:.2f}."
            f"{learning_context}{pattern_context}{domain_context}"
        )

    def _domain_evidence(
        self, intelligence_context: dict[str, Any] | None, tokens: set[str]
    ) -> tuple[dict[str, float], dict[str, Any]]:
        """Bounded, additive evidence derived from Security Knowledge Graph
        entities already detected upstream (IntelligenceContextBuilder).
        Returns an EMPTY distribution (not a dict of zeros) whenever the
        computed magnitude is exactly zero, so the caller's additive loop
        performs zero floating-point operations in that case — the neutral-
        parity guarantee holds by construction, not by arithmetic
        coincidence."""
        mitre_count = 0
        weakness_count = 0
        recommendation_count = 0

        if isinstance(intelligence_context, dict):
            detected = intelligence_context.get("detected_entities")
            if isinstance(detected, list):
                mitre_count = len(detected)
            related = intelligence_context.get("related_entities")
            if isinstance(related, dict):
                for entry in related.values():
                    if not isinstance(entry, dict):
                        continue
                    weaknesses = entry.get("weaknesses")
                    if isinstance(weaknesses, list):
                        weakness_count += len(weaknesses)
                    recommendations = entry.get("recommendations")
                    if isinstance(recommendations, list):
                        recommendation_count += len(recommendations)

        magnitude = min(
            self.DOMAIN_EVIDENCE_CAP,
            0.04 * mitre_count + 0.04 * weakness_count + 0.02 * recommendation_count,
        )
        query_shape = self._domain_query_shape(tokens)
        metadata = {
            "magnitude": round(magnitude, 3),
            "mitre_technique_count": mitre_count,
            "weakness_count": weakness_count,
            "recommendation_count": recommendation_count,
            "query_shape": query_shape,
        }

        if magnitude == 0.0:
            return {}, metadata

        if query_shape == "action":
            distribution = {
                "TOOL_USE": magnitude,
                "PLANNING": 0.4 * magnitude,
                "MEMORY_LOOKUP": 0.0,
            }
        elif query_shape == "informational":
            distribution = {
                "MEMORY_LOOKUP": magnitude,
                "PLANNING": 0.3 * magnitude,
                "TOOL_USE": 0.0,
            }
        else:
            capped = min(magnitude, self.NEUTRAL_DOMAIN_EVIDENCE_CAP)
            distribution = {"PLANNING": capped, "MEMORY_LOOKUP": capped, "TOOL_USE": capped}

        return distribution, metadata

    def _domain_query_shape(self, tokens: set[str]) -> str:
        if tokens & self.action_terms:
            return "action"
        if tokens & self.informational_terms:
            return "informational"
        return "neutral"

    def _normalize(self, scores: dict[str, float]) -> dict[str, float]:
        total = sum(scores.values())
        return {state: round(score / total, 3) for state, score in scores.items()}

    def _tokens(self, text: str) -> set[str]:
        return set(re.findall(r"[a-z0-9]+", text.lower()))
