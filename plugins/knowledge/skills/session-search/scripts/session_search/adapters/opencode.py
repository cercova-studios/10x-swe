from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterator

from ..models import SessionRecord
from ..textutil import content_hash, flatten_text, normalize_body, parse_time, title_from
from .base import HOME, Adapter, ro_sqlite


class OpenCodeAdapter(Adapter):
    name = "opencode"

    def crawl(self) -> Iterator[SessionRecord]:
        path = HOME / ".local" / "share" / "opencode" / "opencode.db"
        if not path.exists():
            return
        conn = ro_sqlite(path)
        try:
            sessions = {
                r["id"]: r
                for r in conn.execute(
                    "SELECT id, title, directory, time_updated, time_created FROM session"
                )
            }
            users: dict[str, list[str]] = defaultdict(list)
            for row in conn.execute(
                """
                SELECT m.session_id AS session_id, m.data AS mdata, p.data AS pdata
                FROM message m
                JOIN part p ON p.message_id = m.id
                """
            ):
                try:
                    mdata = json.loads(row["mdata"]) if row["mdata"] else {}
                    pdata = json.loads(row["pdata"]) if row["pdata"] else {}
                except json.JSONDecodeError:
                    continue
                if not isinstance(mdata, dict) or mdata.get("role") != "user":
                    continue
                if isinstance(pdata, dict) and pdata.get("type") not in (None, "text"):
                    continue
                text = flatten_text(pdata) or flatten_text(mdata)
                if text:
                    users[row["session_id"]].append(text)
            for sid, s in sessions.items():
                texts = users.get(sid, [])
                raw_title = s["title"] or ""
                if raw_title.lower().startswith("new session"):
                    raw_title = ""
                title = title_from(raw_title, *texts)
                body = normalize_body(*texts)
                updated = parse_time(s["time_updated"] or s["time_created"])
                yield SessionRecord(
                    agent=self.name,
                    native_id=sid,
                    cwd=s["directory"] or "",
                    title=title,
                    summary=raw_title or title,
                    body=body,
                    updated_at=updated,
                    source_path=str(path),
                    content_hash=content_hash(title, body, str(updated)),
                )
        finally:
            conn.close()
