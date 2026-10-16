from __future__ import annotations

from .base import HOME
from .jsonl_agent import JsonlAgentAdapter


class PrimeAdapter(JsonlAgentAdapter):
    name = "prime"
    root = HOME / ".prime" / "agent" / "sessions"
