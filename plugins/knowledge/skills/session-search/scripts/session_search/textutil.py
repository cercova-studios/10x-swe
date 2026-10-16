from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import unquote

SECRET_RE = re.compile(
    r"(?i)(sk-[A-Za-z0-9]{10,}|ghp_[A-Za-z0-9]{20,}|xai-[A-Za-z0-9]{10,}"
    r"|Bearer\s+[A-Za-z0-9._\-]{12,}|api[_-]?key[\"'\s:=]+[A-Za-z0-9._\-]{12,})"
)
WS_RE = re.compile(r"\s+")
BODY_MAX = 32_000
TITLE_MAX = 180
SNIPPET_MAX = 240


def flatten_text(value: Any, *, depth: int = 0) -> str:
    if value is None or depth > 6:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", "ignore")
        except Exception:
            return ""
    if isinstance(value, dict):
        if "text" in value and isinstance(value["text"], str):
            return value["text"]
        if "content" in value:
            return flatten_text(value["content"], depth=depth + 1)
        parts = []
        for key in ("message", "display", "summary", "title", "claim"):
            if key in value:
                parts.append(flatten_text(value[key], depth=depth + 1))
        return "\n".join(p for p in parts if p)
    if isinstance(value, list):
        return "\n".join(p for p in (flatten_text(v, depth=depth + 1) for v in value) if p)
    return ""


def redact(text: str) -> str:
    if not text:
        return ""
    return SECRET_RE.sub("[redacted]", text)


def squeeze(text: str) -> str:
    return WS_RE.sub(" ", (text or "").replace("\x00", " ")).strip()


def clip(text: str, n: int) -> str:
    text = squeeze(text)
    if len(text) <= n:
        return text
    return text[: n - 1].rstrip() + "…"


def snippet(text: str, query: str = "", n: int = SNIPPET_MAX) -> str:
    text = squeeze(redact(text))
    if not text:
        return ""
    if query:
        hay = text.lower()
        needle = query.lower().split()[0] if query.split() else query.lower()
        idx = hay.find(needle) if needle else -1
        if idx >= 0:
            start = max(0, idx - 40)
            return clip(text[start:], n)
    return clip(text, n)


def title_from(*parts: str) -> str:
    for part in parts:
        t = clip(redact(part), TITLE_MAX)
        if t:
            return t
    return "(untitled)"


def normalize_body(*parts: str) -> str:
    blob = "\n".join(redact(p) for p in parts if p)
    return clip(blob, BODY_MAX)


def content_hash(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update((p or "").encode("utf-8", "ignore"))
        h.update(b"\0")
    return h.hexdigest()[:16]


def parse_time(value: Any) -> int:
    if value is None or value == "":
        return 0
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        v = float(value)
        if v > 1e14:
            return int(v / 1000)
        if v > 1e12:
            return int(v)
        if v > 1e9:
            return int(v * 1000)
        return int(v)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return 0
        if s.isdigit():
            return parse_time(int(s))
        try:
            s = s.replace("Z", "+00:00")
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp() * 1000)
        except ValueError:
            return 0
    return 0


def decode_cwd(value: str) -> str:
    if not value:
        return ""
    return unquote(value)


def load_json(path) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def parse_since(spec: str | None) -> int | None:
    if not spec:
        return None
    spec = spec.strip().lower()
    now = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
    if spec.endswith("d") and spec[:-1].isdigit():
        return now - int(spec[:-1]) * 86_400_000
    if spec.endswith("h") and spec[:-1].isdigit():
        return now - int(spec[:-1]) * 3_600_000
    if spec.isdigit():
        return parse_time(int(spec))
    t = parse_time(spec)
    return t or None
