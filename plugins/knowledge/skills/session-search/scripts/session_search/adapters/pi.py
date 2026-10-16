from __future__ import annotations

from .base import HOME
from .jsonl_agent import JsonlAgentAdapter


class PiAdapter(JsonlAgentAdapter):
    name = "pi"
    root = HOME / ".pi" / "agent" / "sessions"
