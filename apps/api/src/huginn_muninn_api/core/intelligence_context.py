"""Build lightweight graph intelligence context for API chat requests."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from huginn_muninn_api.core.graph_intelligence_api import GraphIntelligenceApi


MITRE_TECHNIQUE_PATTERN = re.compile(r"\bT\d{4}(?:\.\d{3})?\b", re.IGNORECASE)


class IntelligenceContextBuilder:
    """Create JSON-safe context from existing graph intelligence API data."""

    def __init__(self, repository_root: Path | str) -> None:
        self.repository_root = Path(repository_root)
        self.graph_intelligence = GraphIntelligenceApi(self.repository_root)

    def build(self, message: str) -> dict[str, Any]:
        """Return graph summary and related entities for MITRE IDs in a message."""

        detected_entities = self.detect_mitre_techniques(message)
        related_entities = {
            technique_id: self.graph_intelligence.related(f"mitre:{technique_id}")
            for technique_id in detected_entities
        }
        context = {
            "summary": self.graph_intelligence.summary(),
            "detected_entities": detected_entities,
            "related_entities": related_entities,
        }
        return self._json_safe(context)

    @staticmethod
    def detect_mitre_techniques(message: str) -> list[str]:
        """Detect MITRE ATT&CK technique IDs such as T1059 or T1562.001."""

        matches = {
            match.group(0).upper()
            for match in MITRE_TECHNIQUE_PATTERN.finditer(message or "")
        }
        return sorted(matches)

    @staticmethod
    def _json_safe(payload: dict[str, Any]) -> dict[str, Any]:
        return json.loads(json.dumps(payload, default=str))
