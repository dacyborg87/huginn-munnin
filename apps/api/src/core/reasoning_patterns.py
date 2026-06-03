import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from core.outcome_tracker import Outcome
from huginn_muninn_api.schemas.memory import MemoryRecord


@dataclass
class ContextSignature:
    intent: str
    intent_embedding: list[float]
    memory_relevance_summary: str
    memory_relevance_score: float
    system_state: str
    tokens: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Pattern:
    pattern_id: str
    context_signature: dict[str, Any]
    preferred_path_distribution: dict[str, float]
    success_rate: float
    conditions: dict[str, Any]
    matched_contexts: int = 1
    outcomes: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PatternMatch:
    pattern: Pattern
    similarity: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern_id": self.pattern.pattern_id,
            "similarity": self.similarity,
            "success_rate": self.pattern.success_rate,
            "preferred_path_distribution": self.pattern.preferred_path_distribution,
            "conditions": self.pattern.conditions,
        }


class ReasoningPatternEngine:
    def __init__(self, storage_path: Path | None = None) -> None:
        self.storage_path = storage_path or Path("apps/api/data/reasoning_patterns.json")
        self._patterns: dict[str, Pattern] = {}
        self._lock = Lock()
        self._load()

    def create_context_signature(
        self,
        *,
        message: str,
        intent: str,
        memory: list[MemoryRecord],
        memory_relevance: float,
        system_state: str,
    ) -> ContextSignature:
        tokens = sorted(self._tokens(message))
        return ContextSignature(
            intent=intent,
            intent_embedding=self._mock_embedding(intent, tokens),
            memory_relevance_summary=self._memory_summary(memory),
            memory_relevance_score=round(memory_relevance, 3),
            system_state=system_state,
            tokens=tokens,
        )

    def match_patterns(
        self, signature: ContextSignature, *, min_similarity: float = 0.35, limit: int = 3
    ) -> list[PatternMatch]:
        with self._lock:
            matches = [
                PatternMatch(pattern=pattern, similarity=self._similarity(signature, pattern))
                for pattern in self._patterns.values()
            ]

        filtered = [match for match in matches if match.similarity >= min_similarity]
        filtered.sort(key=lambda match: match.similarity, reverse=True)
        return filtered[:limit]

    def influence_from_matches(self, matches: list[PatternMatch]) -> dict[str, float]:
        influence = {"PLANNING": 0.0, "MEMORY_LOOKUP": 0.0, "TOOL_USE": 0.0}
        for match in matches:
            strength = match.similarity * max(0.0, match.pattern.success_rate - 0.5)
            for path, share in match.pattern.preferred_path_distribution.items():
                influence[path] = influence.get(path, 0.0) + round(strength * share, 3)
        return {path: round(value, 3) for path, value in influence.items()}

    def record_outcome(
        self,
        *,
        signature: ContextSignature,
        chosen_path: str,
        outcome: Outcome,
    ) -> tuple[Pattern, list[str]]:
        with self._lock:
            match = self._best_existing_pattern(signature)
            if match is None or match.similarity < 0.55:
                pattern = Pattern(
                    pattern_id=str(uuid4()),
                    context_signature=signature.to_dict(),
                    preferred_path_distribution={chosen_path: 1.0},
                    success_rate=1.0 if outcome.result == "success" else 0.0,
                    conditions={
                        "intent": signature.intent,
                        "system_state": signature.system_state,
                        "memory_relevance_bucket": self._memory_bucket(
                            signature.memory_relevance_score
                        ),
                    },
                    outcomes=[outcome.to_memory()],
                )
                self._patterns[pattern.pattern_id] = pattern
                matched_contexts = [pattern.pattern_id]
            else:
                pattern = match.pattern
                pattern.outcomes.append(outcome.to_memory())
                pattern.matched_contexts += 1
                pattern.preferred_path_distribution = self._path_distribution(pattern.outcomes)
                pattern.success_rate = self._success_rate(pattern.outcomes)
                pattern.conditions = {
                    **pattern.conditions,
                    "last_result": outcome.result,
                    "memory_relevance_bucket": self._memory_bucket(
                        signature.memory_relevance_score
                    ),
                }
                matched_contexts = [pattern.pattern_id]

            self._save()
            return pattern, matched_contexts

    def _best_existing_pattern(self, signature: ContextSignature) -> PatternMatch | None:
        matches = [
            PatternMatch(pattern=pattern, similarity=self._similarity(signature, pattern))
            for pattern in self._patterns.values()
        ]
        if not matches:
            return None
        return max(matches, key=lambda match: match.similarity)

    def _similarity(self, signature: ContextSignature, pattern: Pattern) -> float:
        pattern_signature = pattern.context_signature
        signature_tokens = set(signature.tokens)
        pattern_tokens = set(pattern_signature.get("tokens", []))
        token_similarity = len(signature_tokens & pattern_tokens) / max(
            len(signature_tokens | pattern_tokens), 1
        )
        intent_similarity = 1.0 if signature.intent == pattern_signature.get("intent") else 0.0
        memory_similarity = 1.0 - min(
            1.0,
            abs(
                signature.memory_relevance_score
                - float(pattern_signature.get("memory_relevance_score", 0.0))
            ),
        )
        state_similarity = (
            1.0 if signature.system_state == pattern_signature.get("system_state") else 0.0
        )
        return round(
            token_similarity * 0.35
            + intent_similarity * 0.35
            + memory_similarity * 0.2
            + state_similarity * 0.1,
            3,
        )

    def _path_distribution(self, outcomes: list[dict[str, Any]]) -> dict[str, float]:
        counts: dict[str, int] = {}
        for outcome in outcomes:
            path = str(outcome.get("chosen_path", "UNKNOWN"))
            counts[path] = counts.get(path, 0) + 1
        total = max(sum(counts.values()), 1)
        return {path: round(count / total, 3) for path, count in counts.items()}

    def _success_rate(self, outcomes: list[dict[str, Any]]) -> float:
        successes = sum(1 for outcome in outcomes if outcome.get("result") == "success")
        return round(successes / max(len(outcomes), 1), 3)

    def _memory_summary(self, memory: list[MemoryRecord]) -> str:
        if not memory:
            return "none"
        tags = sorted({tag for record in memory for tag in record.tags})
        return ",".join(tags[:6]) or "content-match"

    def _mock_embedding(self, intent: str, tokens: list[str]) -> list[float]:
        token_count = len(tokens)
        return [
            round(len(intent) / 20, 3),
            round(min(token_count, 20) / 20, 3),
            round((sum(len(token) for token in tokens) % 17) / 17, 3),
        ]

    def _memory_bucket(self, memory_relevance: float) -> str:
        if memory_relevance >= 0.66:
            return "high"
        if memory_relevance >= 0.25:
            return "medium"
        return "low"

    def _tokens(self, text: str) -> set[str]:
        return set(re.findall(r"[a-z0-9]+", text.lower()))

    def _load(self) -> None:
        if not self.storage_path.exists():
            return
        try:
            raw_patterns = json.loads(self.storage_path.read_text())
        except json.JSONDecodeError:
            return

        self._patterns = {
            raw["pattern_id"]: Pattern(**raw)
            for raw in raw_patterns
            if isinstance(raw, dict) and "pattern_id" in raw
        }

    def _save(self) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_path.write_text(
            json.dumps([pattern.to_dict() for pattern in self._patterns.values()], indent=2)
        )
