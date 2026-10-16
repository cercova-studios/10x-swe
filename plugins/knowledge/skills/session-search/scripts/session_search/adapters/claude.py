from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from ..models import SessionRecord
from ..turns import read_turns
from ..textutil import content_hash, flatten_text, parse_time, title_from
from .base import HOME, Adapter, iter_jsonl


class ClaudeAdapter(Adapter):
    name = "claude"

    def crawl(self) -> Iterator[SessionRecord]:
        root = HOME / ".claude" / "projects"
        if not root.exists():
            return
        for path in root.rglob("*.jsonl"):
            rec = self._from_jsonl(path)
            if rec:
                yield rec

    def _from_jsonl(self, path: Path) -> SessionRecord | None:
        native_id = path.stem
        cwd = ""
        updated = int(path.stat().st_mtime * 1000)
        users: list[str] = []
        session_id = native_id
        for obj in iter_jsonl(path):
            sid = obj.get("sessionId") or obj.get("session_id")
            if sid:
                session_id = str(sid)
            if obj.get("cwd") and not cwd:
                cwd = str(obj["cwd"])
            ts = parse_time(obj.get("timestamp"))
            if ts > updated:
                updated = ts
            if obj.get("type") != "user":
                continue
            text = flatten_text(obj.get("message") or obj.get("content"))
            if text:
                users.append(text)
        limitations = []
        turns = read_turns(path, self.name, limitations)
        if not turns and not users and not cwd:
            return None
        title = title_from(*users)
        body = "\n".join(t.text for t in turns)
        return SessionRecord(
            agent=self.name,
            native_id=session_id,
            cwd=cwd,
            title=title,
            summary=title,
            body=body,
            updated_at=updated,
            source_path=str(path),
            content_hash=content_hash(title, body, str(updated)),
            turns=turns,
            limitations=limitations,
        )
