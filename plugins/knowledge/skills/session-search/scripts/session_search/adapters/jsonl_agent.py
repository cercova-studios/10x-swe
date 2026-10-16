from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from ..models import SessionRecord
from ..textutil import content_hash, flatten_text, normalize_body, parse_time, title_from
from .base import Adapter, iter_jsonl


class JsonlAgentAdapter(Adapter):
    root: Path

    def crawl(self) -> Iterator[SessionRecord]:
        if not self.root.exists():
            return
        for path in self.root.rglob("*.jsonl"):
            rec = self._from_jsonl(path)
            if rec:
                yield rec

    def _from_jsonl(self, path: Path) -> SessionRecord | None:
        native_id = path.stem
        cwd = ""
        title = ""
        updated = int(path.stat().st_mtime * 1000)
        users: list[str] = []
        for obj in iter_jsonl(path):
            kind = obj.get("type")
            ts = parse_time(obj.get("timestamp") or obj.get("updatedAt"))
            if ts > updated:
                updated = ts
            if kind == "session":
                native_id = str(obj.get("id") or native_id)
                if obj.get("cwd"):
                    cwd = str(obj["cwd"])
                title = title or flatten_text(obj.get("title"))
            elif kind in ("title", "title_change"):
                title = flatten_text(obj.get("title")) or title
            elif kind == "message":
                msg = obj.get("message") if isinstance(obj.get("message"), dict) else obj
                role = (msg or {}).get("role")
                if role and role != "user":
                    continue
                text = flatten_text((msg or {}).get("content"))
                if text:
                    users.append(text)
                if len(users) >= 24:
                    break
        if not users and not title:
            return None
        resolved = title_from(title, *users)
        body = normalize_body(*users)
        return SessionRecord(
            agent=self.name,
            native_id=native_id,
            cwd=cwd,
            title=resolved,
            summary=title or resolved,
            body=body,
            updated_at=updated,
            source_path=str(path),
            content_hash=content_hash(resolved, body, str(updated)),
        )
