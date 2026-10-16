from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from ..models import SessionRecord
from ..textutil import content_hash, flatten_text, normalize_body, parse_time, title_from
from .base import HOME, Adapter, ro_sqlite


class CursorAdapter(Adapter):
    name = "cursor"

    def crawl(self) -> Iterator[SessionRecord]:
        path = (
            HOME
            / "Library"
            / "Application Support"
            / "Cursor"
            / "User"
            / "globalStorage"
            / "conversation-search.db"
        )
        if not path.exists():
            return
        conn = ro_sqlite(path)
        try:
            rows = conn.execute(
                """
                SELECT c.id, c.title, c.updated_at, f.body
                FROM conversations c
                LEFT JOIN conversation_fts f ON f.rowid = c.fts_rowid
                """
            )
            for row in rows:
                title = title_from(row["title"] or "")
                body = normalize_body(flatten_text(row["body"]))
                updated = parse_time(row["updated_at"])
                yield SessionRecord(
                    agent=self.name,
                    native_id=str(row["id"]),
                    title=title,
                    summary=title,
                    body=body or title,
                    updated_at=updated,
                    source_path=str(path),
                    content_hash=content_hash(title, body, str(updated)),
                )
        finally:
            conn.close()
