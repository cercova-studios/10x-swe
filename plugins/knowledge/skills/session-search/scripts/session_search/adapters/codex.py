from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path

from ..models import SessionRecord
from ..turns import read_turns
from ..textutil import content_hash, flatten_text, normalize_body, parse_time, title_from
from .base import HOME, Adapter, iter_jsonl


class CodexAdapter(Adapter):
    name = "codex"

    def crawl(self) -> Iterator[SessionRecord]:
        root = HOME / ".codex"
        index = {}
        idx_path = root / "session_index.jsonl"
        if idx_path.exists():
            for obj in iter_jsonl(idx_path):
                if obj.get("id"):
                    index[str(obj["id"])] = obj
        history: dict[str, list[str]] = defaultdict(list)
        hist_path = root / "history.jsonl"
        if hist_path.exists():
            for obj in iter_jsonl(hist_path):
                sid = str(obj.get("session_id") or "")
                text = flatten_text(obj.get("text"))
                if sid and text:
                    history[sid].append(text)
        sessions_dir = root / "sessions"
        seen: set[str] = set()
        if sessions_dir.exists():
            for path in sessions_dir.rglob("*.jsonl"):
                seen.add(path.stem[-36:])
                rec = self._from_rollout(path, index, history)
                if rec:
                    seen.add(rec.native_id)
                    yield rec
        for sid, obj in index.items():
            if sid in seen:
                continue
            texts = history.get(sid, [])
            title = title_from(obj.get("thread_name") or "", *texts)
            body = normalize_body(*texts)
            updated = parse_time(obj.get("updated_at"))
            yield SessionRecord(
                agent=self.name,
                native_id=sid,
                title=title,
                summary=title,
                body=body,
                updated_at=updated,
                source_path=str(idx_path),
                content_hash=content_hash(title, body, str(updated)),
            )

    def _from_rollout(
        self,
        path: Path,
        index: dict,
        history: dict[str, list[str]],
    ) -> SessionRecord | None:
        native_id = path.stem
        if native_id.startswith("rollout-") and len(native_id) > 36:
            native_id = native_id[-36:]
        cwd = ""
        updated = int(path.stat().st_mtime * 1000)
        users: list[str] = []
        meta_title = ""
        for obj in iter_jsonl(path):
            ts = parse_time(obj.get("timestamp"))
            if ts > updated:
                updated = ts
            payload = obj.get("payload")
            if not isinstance(payload, dict):
                continue
            if payload.get("cwd") and not cwd:
                cwd = str(payload["cwd"])
            ptype = payload.get("type")
            if obj.get("type") == "session_meta":
                source = payload.get('source')
                if isinstance(source, dict) and isinstance(source.get('subagent'), dict) and source['subagent'].get('other') == 'guardian':
                    return None
                native_id = str(payload.get("id") or native_id)
                meta_title = flatten_text(payload.get("summary") or payload.get("name"))
            if ptype == "user_message" or payload.get("role") == "user":
                text = flatten_text(payload.get("message") or payload.get("content"))
                if text:
                    users.append(text)
        idx = index.get(native_id) or {}
        limitations = []
        turns = read_turns(path, self.name, limitations)
        texts = [t.text for t in turns] or users or history.get(native_id, [])
        if not texts and not idx:
            return None
        title = title_from(idx.get("thread_name") or "", meta_title, *texts)
        body = "\n".join(texts) if turns else normalize_body(*texts)
        updated = max(updated, parse_time(idx.get("updated_at")))
        return SessionRecord(
            agent=self.name,
            native_id=native_id,
            cwd=cwd,
            title=title,
            summary=idx.get("thread_name") or title,
            body=body,
            updated_at=updated,
            source_path=str(path),
            content_hash=content_hash(title, body, str(updated)),
            turns=turns,
            limitations=limitations,
        )
