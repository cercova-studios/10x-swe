from __future__ import annotations

from ..models import SearchResult, StrategyUnavailable
from ..store import Store


class SemanticStrategy:
    name = "semantic"

    def __init__(self, store: Store) -> None:
        self.store = store

    def search(
        self,
        query: str,
        *,
        last: bool = False,
        limit: int = 10,
        agent: str | None = None,
        since_ms: int | None = None,
    ) -> SearchResult:
        if self.store.embedding_count() == 0:
            raise StrategyUnavailable(self.name, "no embeddings; run session-search index")
        hits = self.store.semantic_search(
            query, limit=1 if last else limit, agent=agent, since_ms=since_ms, last=last
        )
        return SearchResult(
            query=query,
            mode="semantic",
            hits=hits,
            strategies_used=["semantic"],
        )
