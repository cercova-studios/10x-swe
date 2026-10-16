from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Iterator
from urllib.parse import unquote, urlparse

from ..models import SessionRecord
from ..textutil import content_hash, flatten_text, normalize_body, parse_time, title_from
from .base import HOME, Adapter, iter_jsonl

THREAD_LIMIT = int(os.environ.get("SESSION_SEARCH_AMP_LIMIT", "200"))
EXPORT_TIMEOUT = int(os.environ.get("SESSION_SEARCH_AMP_EXPORT_TIMEOUT", "30"))


class AmpAdapter(Adapter):
    name = "amp"

    def crawl(self) -> Iterator[SessionRecord]:
        cloud = list(self._from_cloud())
        seen = {r.native_id for r in cloud}
        yield from cloud
        if cloud:
            return
        yield from self._from_history(seen)

    def _from_history(self, seen: set[str]) -> Iterator[SessionRecord]:
        path = HOME / ".local" / "share" / "amp" / "history.jsonl"
        if not path.exists():
            return
        for i, obj in enumerate(iter_jsonl(path)):
            native_id = str(obj.get("id") or f"history:{i}")
            if native_id in seen:
                continue
            text = flatten_text(obj.get("text") or obj.get("prompt"))
            if not text:
                continue
            cwd = str(obj.get("cwd") or "")
            updated = parse_time(obj.get("ts") or obj.get("timestamp") or obj.get("createdAt"))
            if not updated:
                updated = int(path.stat().st_mtime * 1000)
            title = title_from(text)
            body = normalize_body(text)
            yield SessionRecord(
                agent=self.name,
                native_id=native_id,
                cwd=cwd,
                title=title,
                summary=title,
                body=body,
                updated_at=updated,
                source_path=str(path),
                content_hash=content_hash(title, body, str(updated)),
            )

    def _from_cloud(self) -> Iterator[SessionRecord]:
        if not shutil.which("amp"):
            return
        threads = self._list_threads()
        for meta in threads[:THREAD_LIMIT]:
            tid = str(meta.get("id") or "")
            if not tid:
                continue
            exported = self._export_thread(tid)
            rec = self._record_from_export(tid, meta, exported)
            if rec:
                yield rec

    def _list_threads(self) -> list[dict]:
        items: list[dict] = []
        offset = 0
        page = 50
        while offset < THREAD_LIMIT:
            raw = _amp_json(
                ["threads", "list", "--json", "--include-archived", "--limit", str(page), "--offset", str(offset)]
            )
            if not isinstance(raw, list) or not raw:
                break
            items.extend(r for r in raw if isinstance(r, dict))
            if len(raw) < page:
                break
            offset += page
        return items

    def _export_thread(self, thread_id: str) -> dict | None:
        raw = _amp_json(["threads", "export", thread_id], timeout=EXPORT_TIMEOUT)
        return raw if isinstance(raw, dict) else None

    def _record_from_export(self, tid: str, meta: dict, exported: dict | None) -> SessionRecord | None:
        title = flatten_text((exported or {}).get("title") or meta.get("title"))
        cwd = _cwd_from(exported) or _file_url(str(meta.get("tree") or ""))
        updated = parse_time(
            (exported or {}).get("updatedAt")
            or (exported or {}).get("created")
            or meta.get("updated")
        )
        users: list[str] = []
        for msg in (exported or {}).get("messages") or []:
            if not isinstance(msg, dict):
                continue
            if msg.get("role") not in ("user", "human"):
                continue
            text = flatten_text(msg.get("content"))
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
            native_id=tid,
            cwd=cwd,
            title=resolved,
            summary=title or resolved,
            body=body,
            updated_at=updated,
            source_path=f"amp://threads/{tid}",
            content_hash=content_hash(resolved, body, str(updated)),
        )


def _amp_json(args: list[str], timeout: int = 20) -> object | None:
    try:
        proc = subprocess.run(
            ["amp", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def _cwd_from(exported: dict | None) -> str:
    if not exported:
        return ""
    env = exported.get("env") if isinstance(exported.get("env"), dict) else {}
    initial = env.get("initial") if isinstance(env.get("initial"), dict) else {}
    return _file_url(str(initial.get("workingDirectory") or ""))


def _file_url(value: str) -> str:
    if not value:
        return ""
    if value.startswith("file://"):
        return unquote(urlparse(value).path)
    return value
