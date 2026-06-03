from datetime import UTC, datetime
import re
from uuid import uuid4

from huginn_muninn_api.schemas.memory import MemoryRecord, MemorySearchRequest


class MuninnMemory:
    def __init__(self) -> None:
        self._records: list[MemoryRecord] = []

    def write(self, record: MemoryRecord) -> MemoryRecord:
        stored = record.model_copy(
            update={
                "id": record.id or str(uuid4()),
                "created_at": record.created_at or datetime.now(UTC),
            }
        )
        self._records.append(stored)
        return stored

    def search(self, request: MemorySearchRequest) -> list[MemoryRecord]:
        query = request.query.lower()
        query_tokens = self._tokens(query)
        scored_results: list[tuple[float, MemoryRecord]] = []

        for record in self._records:
            if request.namespace is not None and record.namespace != request.namespace:
                continue

            content = record.content.lower()
            record_tokens = self._tokens(content)
            exact_match = query in content
            token_overlap = len(query_tokens & record_tokens) / max(len(query_tokens), 1)

            if exact_match or token_overlap > 0:
                score = 1.0 if exact_match else token_overlap
                scored_results.append((score, record))

        scored_results.sort(key=lambda result: result[0], reverse=True)
        return [record for _, record in scored_results[: request.limit]]

    def _tokens(self, text: str) -> set[str]:
        return set(re.findall(r"[a-z0-9]+", text.lower()))
