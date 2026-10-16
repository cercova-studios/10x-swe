from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path

from ..models import SessionRecord
from ..textutil import content_hash, flatten_text, normalize_body, parse_time, title_from
from .base import HOME, Adapter, ro_sqlite


class CopilotAdapter(Adapter):
    name = "copilot"

    def crawl(self) -> Iterator[SessionRecord]:
        path = HOME / ".copilot" / "session-store.db"
        if not path.exists():
            return
        conn = ro_sqlite(path)
        try:
            turns: dict[str, list[str]] = defaultdict(list)
            for row in conn.execute(
                "SELECT session_id, user_message, timestamp FROM turns ORDER BY turn_index"
            ):
                text = flatten_text(row["user_message"])
                if text:
                    turns[row["session_id"]].append(text)
            for row in conn.execute(
                "SELECT id, cwd, summary, created_at, updated_at FROM sessions"
            ):
                texts = turns.get(row["id"], [])
                summary = flatten_text(row["summary"])
                title = title_from(summary, *texts)
                body = normalize_body(summary, *texts)
                updated = parse_time(row["updated_at"] or row["created_at"])
                yield SessionRecord(
                    agent=self.name,
                    native_id=row["id"],
                    cwd=row["cwd"] or "",
                    title=title,
                    summary=summary or title,
                    body=body,
                    updated_at=updated,
                    source_path=str(path),
                    content_hash=content_hash(title, body, str(updated)),
                )
        finally:
            conn.close()
