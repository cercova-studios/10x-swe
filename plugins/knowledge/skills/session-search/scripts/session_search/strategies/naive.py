from __future__ import annotations

from ..models import SearchResult
from ..store import Store


class NaiveStrategy:
    name = "naive"

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
        hits = self.store.search(
            query,
            limit=1 if last else limit,
            agent=agent,
            since_ms=since_ms,
            order="recency" if last else "rank",
            strategy=self.name,
        )
        return SearchResult(
            query=query,
            mode="naive",
            hits=hits,
            strategies_used=["naive"],
        )
