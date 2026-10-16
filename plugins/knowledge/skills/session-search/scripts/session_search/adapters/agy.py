from __future__ import annotations

import sqlite3
from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path

from ..models import SessionRecord
from ..textutil import content_hash, flatten_text, normalize_body, parse_time, title_from
from .base import HOME, Adapter, iter_jsonl, ro_sqlite

CLI_ROOTS = (
    HOME / ".gemini" / "antigravity-cli",
    HOME / ".gemini" / "antigravity",
)


class AgyAdapter(Adapter):
    name = "agy"

    def crawl(self) -> Iterator[SessionRecord]:
        seen: set[str] = set()
        for root in CLI_ROOTS:
            for rec in self._from_history(root / "history.jsonl"):
                if rec.native_id in seen:
                    continue
                seen.add(rec.native_id)
                yield rec
            for rec in self._from_summaries(root / "conversation_summaries.db"):
                if rec.native_id in seen:
                    continue
                seen.add(rec.native_id)
                yield rec

    def _from_history(self, path: Path) -> Iterator[SessionRecord]:
        if not path.exists():
            return
        by_ws: dict[str, list[tuple[int, str]]] = defaultdict(list)
        for obj in iter_jsonl(path):
            text = flatten_text(obj.get("display") or obj.get("content"))
            if not text:
                continue
            ws = str(obj.get("workspace") or "global")
            ts = parse_time(obj.get("timestamp"))
            by_ws[ws].append((ts, text))
        for ws, items in by_ws.items():
            items.sort(key=lambda x: x[0])
            texts = [t for _, t in items]
            updated = max((ts for ts, _ in items), default=int(path.stat().st_mtime * 1000))
            title = title_from(*texts)
            body = normalize_body(*texts)
            yield SessionRecord(
                agent=self.name,
                native_id=f"history:{ws}",
                cwd=ws if ws != "global" else "",
                title=title,
                summary=title,
                body=body,
                updated_at=updated,
                source_path=str(path),
                content_hash=content_hash(title, body, str(updated)),
            )

    def _from_summaries(self, path: Path) -> Iterator[SessionRecord]:
        if not path.exists():
            return
        try:
            conn = ro_sqlite(path)
        except sqlite3.Error:
            return
        try:
            tables = [
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            ]
            for table in tables:
                cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
                colset = {c.lower() for c in cols}
                if not ({"title", "summary", "text", "content"} & colset):
                    continue
                id_col = next((c for c in cols if c.lower() in ("id", "conversation_id", "session_id")), cols[0])
                title_col = next((c for c in cols if c.lower() in ("title", "name")), None)
                body_col = next((c for c in cols if c.lower() in ("summary", "text", "content", "body")), None)
                time_col = next((c for c in cols if "time" in c.lower() or "updated" in c.lower()), None)
                cwd_col = next((c for c in cols if c.lower() in ("cwd", "workspace", "directory")), None)
                select = [id_col]
                for c in (title_col, body_col, time_col, cwd_col):
                    if c and c not in select:
                        select.append(c)
                for row in conn.execute(f"SELECT {', '.join(select)} FROM {table}"):
                    native_id = f"sum:{row[id_col]}"
                    title = title_from(row[title_col] if title_col else "", flatten_text(row[body_col] if body_col else ""))
                    body = normalize_body(flatten_text(row[body_col] if body_col else ""))
                    updated = parse_time(row[time_col] if time_col else 0)
                    yield SessionRecord(
                        agent=self.name,
                        native_id=native_id,
                        cwd=str(row[cwd_col] or "") if cwd_col else "",
                        title=title,
                        summary=title,
                        body=body or title,
                        updated_at=updated,
                        source_path=str(path),
                        content_hash=content_hash(title, body, str(updated)),
                    )
        except sqlite3.Error:
            return
        finally:
            conn.close()
