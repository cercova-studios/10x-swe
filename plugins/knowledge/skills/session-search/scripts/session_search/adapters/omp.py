from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator

from ..models import SessionRecord
from ..textutil import content_hash, flatten_text, normalize_body, parse_time, title_from
from .base import HOME, ro_sqlite
from .jsonl_agent import JsonlAgentAdapter


class OmpAdapter(JsonlAgentAdapter):
    name = "omp"
    root = HOME / ".omp" / "agent" / "sessions"

    def crawl(self) -> Iterator[SessionRecord]:
        seen: set[str] = set()
        for rec in super().crawl():
            seen.add(rec.native_id)
            yield rec
        db = HOME / ".omp" / "agent" / "history.db"
        if not db.exists():
            return
        conn = ro_sqlite(db)
        try:
            titles = {
                r["session_id"]: (r["title"], r["updated_at"])
                for r in conn.execute("SELECT session_id, title, updated_at FROM session_titles")
            }
            by_sid: dict[str, list[tuple[int, str, str]]] = defaultdict(list)
            for row in conn.execute(
                "SELECT session_id, prompt, created_at, cwd FROM history ORDER BY id"
            ):
                sid = row["session_id"] or "history"
                by_sid[sid].append(
                    (parse_time(row["created_at"]), flatten_text(row["prompt"]), row["cwd"] or "")
                )
            for sid, items in by_sid.items():
                if sid in seen:
                    continue
                texts = [t for _, t, _ in items if t]
                cwd = next((c for _, _, c in reversed(items) if c), "")
                raw_title, raw_updated = titles.get(sid, ("", 0))
                updated = max(parse_time(raw_updated), max((ts for ts, _, _ in items), default=0))
                title = title_from(flatten_text(raw_title), *texts)
                body = normalize_body(*texts)
                yield SessionRecord(
                    agent=self.name,
                    native_id=str(sid),
                    cwd=cwd,
                    title=title,
                    summary=title,
                    body=body,
                    updated_at=updated,
                    source_path=str(db),
                    content_hash=content_hash(title, body, str(updated)),
                )
        finally:
            conn.close()
