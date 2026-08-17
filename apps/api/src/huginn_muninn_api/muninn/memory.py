from core.stores.memory_store import InMemoryMemoryStore, MemoryStore
from huginn_muninn_api.schemas.memory import MemoryRecord, MemorySearchRequest


class MuninnMemory:
    def __init__(self, store: MemoryStore | None = None) -> None:
        self._store = store or InMemoryMemoryStore()

    def bind_store(self, store: MemoryStore) -> None:
        """Swap the backing store (used at startup to switch memory -> postgres)."""
        self._store = store

    async def write(self, record: MemoryRecord) -> MemoryRecord:
        return await self._store.write(record)

    async def search(self, request: MemorySearchRequest) -> list[MemoryRecord]:
        return await self._store.search(request)
