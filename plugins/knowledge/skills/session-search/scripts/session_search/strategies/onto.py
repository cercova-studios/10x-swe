from __future__ import annotations

from ..models import SearchResult, StrategyUnavailable
from ..store import Store


class OntoStrategy:
    name = "onto"

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
        if self.store.insight_count() == 0:
            raise StrategyUnavailable(self.name, "no insight graph; run session-search index")
        hits = self.store.insight_search(
            query, limit=1 if last else limit, agent=agent, since_ms=since_ms, last=last
        )
        return SearchResult(
            query=query,
            mode="onto",
            hits=hits,
            strategies_used=["onto"],
        )
