from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from ..models import SessionRecord
from ..textutil import (
    content_hash,
    decode_cwd,
    flatten_text,
    normalize_body,
    parse_time,
    title_from,
)
from .base import HOME, Adapter, iter_jsonl


class GrokAdapter(Adapter):
    name = "grok"

    def crawl(self) -> Iterator[SessionRecord]:
        root = HOME / ".grok" / "sessions"
        if not root.exists():
            return
        for summary in root.rglob("summary.json"):
            rec = self._from_session_dir(summary.parent)
            if rec:
                yield rec

    def _from_session_dir(self, folder: Path) -> SessionRecord | None:
        summary_path = folder / "summary.json"
        try:
            data = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        info = data.get("info") if isinstance(data.get("info"), dict) else {}
        native_id = str(info.get("id") or folder.name)
        cwd = str(info.get("cwd") or decode_cwd(folder.parent.name))
        updated = parse_time(data.get("last_active_at") or data.get("updated_at"))
        if not updated:
            updated = int(summary_path.stat().st_mtime * 1000)
        users: list[str] = []
        chat = folder / "chat_history.jsonl"
        if chat.exists():
            for obj in iter_jsonl(chat):
                if obj.get("type") not in ("user", "human"):
                    continue
                text = flatten_text(obj.get("content") or obj.get("message"))
                if text:
                    users.append(text)
                if len(users) >= 24:
                    break
        summary = flatten_text(data.get("session_summary"))
        if not users and not summary:
            return None
        title = title_from(summary, *users)
        body = normalize_body(summary, *users)
        return SessionRecord(
            agent=self.name,
            native_id=native_id,
            cwd=cwd,
            title=title,
            summary=summary or title,
            body=body,
            updated_at=updated,
            source_path=str(folder),
            content_hash=content_hash(title, body, str(updated)),
        )
