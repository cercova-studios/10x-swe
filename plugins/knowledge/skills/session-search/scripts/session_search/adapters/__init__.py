from __future__ import annotations

from collections.abc import Iterator

from ..models import SessionRecord
from .agy import AgyAdapter
from .amp import AmpAdapter
from .claude import ClaudeAdapter
from .codex import CodexAdapter
from .copilot import CopilotAdapter
from .cursor import CursorAdapter
from .grok import GrokAdapter
from .omp import OmpAdapter
from .opencode import OpenCodeAdapter
from .pi import PiAdapter
from .prime import PrimeAdapter

ADAPTERS = {
    "claude": ClaudeAdapter,
    "codex": CodexAdapter,
    "cursor": CursorAdapter,
    "grok": GrokAdapter,
    "copilot": CopilotAdapter,
    "agy": AgyAdapter,
    "opencode": OpenCodeAdapter,
    "amp": AmpAdapter,
    "omp": OmpAdapter,
    "prime": PrimeAdapter,
    "pi": PiAdapter,
}

ALIASES = {
    "gemini": "agy",
    "antigravity": "agy",
    "cursor-agent": "cursor",
    "prime-agent": "prime",
}

SUPERSEDED = {
    "agy": ["gemini"],
}


def resolve_agent(name: str) -> str:
    return ALIASES.get(name, name)


def agent_choices() -> list[str]:
    return sorted(set(ADAPTERS) | set(ALIASES))


def crawl(agent: str | None = None) -> Iterator[tuple[str, list[SessionRecord], str | None]]:
    if agent:
        names = [resolve_agent(agent)]
    else:
        names = list(ADAPTERS)
    for name in names:
        cls = ADAPTERS.get(name)
        if cls is None:
            yield name, [], f"unknown adapter {name!r}"
            continue
        try:
            records = list(cls().crawl())
            yield name, records, None
        except Exception as exc:  # noqa: BLE001
            yield name, [], str(exc)
