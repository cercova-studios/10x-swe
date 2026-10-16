from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(slots=True)
class Turn:
    line: int
    role: str
    text: str
    timestamp: str | None
    pointer: str
    record_sha256: str
    original_sha256: str
    redacted: bool


@dataclass(slots=True)
class SessionRecord:
    agent: str
    native_id: str
    cwd: str = ""
    title: str = ""
    summary: str = ""
    body: str = ""
    updated_at: int = 0
    source_path: str = ""
    content_hash: str = ""
    turns: list[Turn] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        return f"{self.agent}:{self.native_id}"


@dataclass(slots=True)
class Hit:
    agent: str
    native_id: str
    cwd: str
    title: str
    summary: str
    snippet: str
    updated_at: int
    source_path: str
    strategy: str
    rank: float = 0.0
    citations: list[dict] = field(default_factory=list)

    @property
    def id(self) -> str:
        return f"{self.agent}:{self.native_id}"

    def as_dict(self) -> dict:
        d = asdict(self)
        d["id"] = self.id
        return d


@dataclass(slots=True)
class SearchResult:
    query: str
    mode: str
    hits: list[Hit] = field(default_factory=list)
    strategies_used: list[str] = field(default_factory=list)
    strategies_skipped: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "query": self.query,
            "mode": self.mode,
            "strategies_used": self.strategies_used,
            "strategies_skipped": self.strategies_skipped,
            "hits": [h.as_dict() for h in self.hits],
        }


class StrategyUnavailable(Exception):
    def __init__(self, name: str, reason: str) -> None:
        super().__init__(reason)
        self.name = name
        self.reason = reason
