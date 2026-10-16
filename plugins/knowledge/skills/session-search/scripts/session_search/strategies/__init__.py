from __future__ import annotations

from ..models import SearchResult, StrategyUnavailable
from ..store import Store
from .auto import AutoStrategy
from .naive import NaiveStrategy
from .onto import OntoStrategy
from .semantic import SemanticStrategy

STRATEGIES = {
    "naive": NaiveStrategy,
    "semantic": SemanticStrategy,
    "onto": OntoStrategy,
    "auto": AutoStrategy,
}


def run(
    store: Store,
    query: str,
    *,
    mode: str = "auto",
    last: bool = False,
    limit: int = 10,
    agent: str | None = None,
    since_ms: int | None = None,
) -> SearchResult:
    cls = STRATEGIES.get(mode)
    if cls is None:
        raise StrategyUnavailable(mode, f"unknown mode {mode!r}")
    return cls(store).search(
        query, last=last, limit=limit, agent=agent, since_ms=since_ms
    )
