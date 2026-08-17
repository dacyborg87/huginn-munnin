"""Reasoning-pattern data types.

Split out of reasoning_patterns.py so core/stores/pattern_store.py can
depend on Pattern without a circular import (reasoning_patterns.py in turn
depends on the store implementations). No fields, shapes, or math changed —
pure relocation of ContextSignature, Pattern, and PatternMatch.
"""

from dataclasses import asdict, dataclass, field
from typing import Any


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
