from __future__ import annotations

from ..models import SearchResult, StrategyUnavailable
from ..store import Store
from .naive import NaiveStrategy
from .onto import OntoStrategy
from .semantic import SemanticStrategy


class AutoStrategy:
    name = "auto"

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
        skipped: dict[str, str] = {}
        used: list[str] = []
        kwargs = dict(last=last, limit=limit, agent=agent, since_ms=since_ms)

        onto_hits = []
        try:
            onto = OntoStrategy(self.store).search(query, **kwargs)
            onto_hits = onto.hits
            used.append("onto")
        except StrategyUnavailable as exc:
            skipped[exc.name] = exc.reason

        naive = NaiveStrategy(self.store).search(query, **kwargs)
        used.append("naive")
        hits = list(onto_hits)
        seen = {h.id for h in hits}
        for hit in naive.hits:
            if hit.id not in seen:
                hits.append(hit)
                seen.add(hit.id)

        if not last and len(hits) < 3:
            try:
                sem = SemanticStrategy(self.store).search(query, **kwargs)
                used.append("semantic")
                for hit in sem.hits:
                    if hit.id not in seen:
                        hits.append(hit)
                        seen.add(hit.id)
            except StrategyUnavailable as exc:
                skipped[exc.name] = exc.reason
        else:
            skipped.setdefault("semantic", "not needed (naive/onto recall)")

        if last:
            hits = sorted(hits, key=lambda h: h.updated_at, reverse=True)[:1]
        else:
            hits = hits[:limit]
        return SearchResult(
            query=query,
            mode="auto",
            hits=hits,
            strategies_used=used,
            strategies_skipped=skipped,
        )
