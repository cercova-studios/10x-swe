from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from .models import SessionRecord
from .textutil import clip, redact, squeeze

REJECT_RE = re.compile(r"\b(don't|do not|instead of|rejected|not a |avoid|never)\b", re.I)
DECIDE_RE = re.compile(r"\b(locked|we'll use|we will use|decided|v1:|ship)\b", re.I)

ALIASES = {
    "session analytics": "session-search",
    "session-analytics": "session-search",
    "conversation history": "session-search",
    "conversation search": "session-search",
    "gemini": "agy",
    "antigravity": "agy",
    "cursor-agent": "cursor",
    "prime-agent": "prime",
    "bm25": "lexical-search",
    "bm42": "lexical-search",
    "similarity search": "semantic-search",
    "embeddings": "semantic-search",
    "insight graph": "onto-search",
    "ontological": "onto-search",
}


@dataclass(slots=True)
class Insight:
    kind: str
    claim: str
    session_id: str
    agent: str
    cwd: str
    updated_at: int
    confidence: float
    extractor: str

    @property
    def id(self) -> str:
        digest = hashlib.sha256(f"{self.session_id}:{self.kind}:{self.claim}".encode()).hexdigest()[:12]
        return f"{self.session_id}:{self.kind}:{digest}"


def extract_insights(rec: SessionRecord) -> list[Insight]:
    title = squeeze(redact(rec.title or ""))
    summary = squeeze(redact(rec.summary or ""))
    body = squeeze(redact(rec.body or ""))
    head = clip(title or summary or body, 180)
    if not head or head.lower().startswith("new session") or head == "(untitled)":
        return []
    kind = "finding"
    if REJECT_RE.search(head):
        kind = "rejection"
    elif DECIDE_RE.search(head):
        kind = "decision"
    return [
        Insight(
            kind=kind,
            claim=head,
            session_id=rec.id,
            agent=rec.agent,
            cwd=rec.cwd,
            updated_at=rec.updated_at,
            confidence=0.6 if kind == "finding" else 0.75,
            extractor="heuristic",
        )
    ]


def expand_query(query: str) -> list[str]:
    q = squeeze(query).lower()
    extra = [ALIASES[k] for k in ALIASES if k in q]
    return [query, *extra]
