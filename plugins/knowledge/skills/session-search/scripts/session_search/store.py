from __future__ import annotations

import os
import json
from dataclasses import asdict
import sqlite3
from pathlib import Path

from .models import Hit, SessionRecord, Turn
from .textutil import snippet

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  agent TEXT NOT NULL,
  native_id TEXT NOT NULL,
  cwd TEXT,
  title TEXT,
  summary TEXT,
  body TEXT,
  updated_at INTEGER NOT NULL DEFAULT 0,
  source_path TEXT,
  content_hash TEXT
);
CREATE INDEX IF NOT EXISTS sessions_agent ON sessions(agent);
CREATE INDEX IF NOT EXISTS sessions_updated ON sessions(updated_at DESC);
CREATE VIRTUAL TABLE IF NOT EXISTS sessions_fts USING fts5(
  title,
  summary,
  body,
  content='sessions',
  content_rowid='rowid',
  tokenize='porter unicode61'
);
CREATE TRIGGER IF NOT EXISTS sessions_ai AFTER INSERT ON sessions BEGIN
  INSERT INTO sessions_fts(rowid, title, summary, body)
  VALUES (new.rowid, new.title, new.summary, new.body);
END;
CREATE TRIGGER IF NOT EXISTS sessions_ad AFTER DELETE ON sessions BEGIN
  INSERT INTO sessions_fts(sessions_fts, rowid, title, summary, body)
  VALUES ('delete', old.rowid, old.title, old.summary, old.body);
END;
CREATE TRIGGER IF NOT EXISTS sessions_au AFTER UPDATE ON sessions BEGIN
  INSERT INTO sessions_fts(sessions_fts, rowid, title, summary, body)
  VALUES ('delete', old.rowid, old.title, old.summary, old.body);
  INSERT INTO sessions_fts(rowid, title, summary, body)
  VALUES (new.rowid, new.title, new.summary, new.body);
END;
CREATE TABLE IF NOT EXISTS embeddings (
  id TEXT PRIMARY KEY,
  agent TEXT NOT NULL,
  dim INTEGER NOT NULL,
  embedder TEXT NOT NULL,
  vec BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS insights (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  claim TEXT NOT NULL,
  session_id TEXT NOT NULL,
  agent TEXT NOT NULL,
  cwd TEXT,
  updated_at INTEGER NOT NULL DEFAULT 0,
  confidence REAL NOT NULL DEFAULT 0,
  extractor TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS insights_agent ON insights(agent);
CREATE INDEX IF NOT EXISTS insights_session ON insights(session_id);
CREATE VIRTUAL TABLE IF NOT EXISTS insights_fts USING fts5(
  claim,
  kind,
  content='insights',
  content_rowid='rowid',
  tokenize='porter unicode61'
);
CREATE TRIGGER IF NOT EXISTS insights_ai AFTER INSERT ON insights BEGIN
  INSERT INTO insights_fts(rowid, claim, kind)
  VALUES (new.rowid, new.claim, new.kind);
END;
CREATE TRIGGER IF NOT EXISTS insights_ad AFTER DELETE ON insights BEGIN
  INSERT INTO insights_fts(insights_fts, rowid, claim, kind)
  VALUES ('delete', old.rowid, old.claim, old.kind);
END;

"""


def default_db_path() -> Path:
    override = os.environ.get("SESSION_SEARCH_DB")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".local" / "share" / "session-search" / "index.db"


class Store:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.executescript(SCHEMA)
        if 'turns_json' not in {r[1] for r in self.conn.execute('PRAGMA table_info(sessions)')}:
            self.conn.execute("ALTER TABLE sessions ADD COLUMN turns_json TEXT NOT NULL DEFAULT '[]'")
            self.conn.commit()
        if 'limitations_json' not in {r[1] for r in self.conn.execute('PRAGMA table_info(sessions)')}:
            self.conn.execute("ALTER TABLE sessions ADD COLUMN limitations_json TEXT NOT NULL DEFAULT '[]'")
            self.conn.commit()
        os.chmod(self.path, 0o600)

    def close(self) -> None:
        self.conn.close()

    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        self.conn.commit()

    def get_meta(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None

    def replace_agent(self, agent: str, records: list[SessionRecord]) -> int:
        with self.conn:
            return self._replace_agent(agent, records)

    def _replace_agent(self, agent: str, records: list[SessionRecord]) -> int:
        uniq: dict[str, SessionRecord] = {}
        for rec in records:
            prev = uniq.get(rec.id)
            if prev is None or rec.updated_at >= prev.updated_at:
                uniq[rec.id] = rec
        records = list(uniq.values())
        self.conn.execute("DELETE FROM embeddings WHERE agent=?", (agent,))
        self.conn.execute("DELETE FROM insights WHERE agent=?", (agent,))
        self.conn.execute("DELETE FROM sessions WHERE agent=?", (agent,))
        self.conn.executemany(
            """
            INSERT INTO sessions(
              id, agent, native_id, cwd, title, summary, body, updated_at, source_path, content_hash, turns_json, limitations_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    r.id,
                    r.agent,
                    r.native_id,
                    r.cwd,
                    r.title,
                    r.summary,
                    r.body,
                    r.updated_at,
                    r.source_path,
                    r.content_hash,
                    json.dumps([asdict(t) for t in r.turns]),
                    json.dumps(r.limitations),
                )
                for r in records
            ],
        )
        if records:
            self.enrich(records, agent=agent, commit=False)
        return len(records)

    def all_records(self, agent: str | None = None) -> list[SessionRecord]:
        if agent:
            rows = self.conn.execute("SELECT * FROM sessions WHERE agent=?", (agent,)).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM sessions").fetchall()
        return [
            SessionRecord(
                agent=row["agent"],
                native_id=row["native_id"],
                cwd=row["cwd"] or "",
                title=row["title"] or "",
                summary=row["summary"] or "",
                body=row["body"] or "",
                updated_at=int(row["updated_at"] or 0),
                source_path=row["source_path"] or "",
                content_hash=row["content_hash"] or "",
                turns=[Turn(**t) for t in json.loads(row["turns_json"])],
                limitations=json.loads(row["limitations_json"]),
            )
            for row in rows
        ]

    def count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()
        return int(row["n"])

    def counts_by_agent(self) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT agent, COUNT(*) AS n FROM sessions GROUP BY agent ORDER BY agent"
        ).fetchall()
        return {r["agent"]: int(r["n"]) for r in rows}

    def get(self, agent: str, native_id: str) -> SessionRecord | None:
        row = self.conn.execute(
            "SELECT * FROM sessions WHERE agent=? AND native_id=?",
            (agent, native_id),
        ).fetchone()
        if row is None:
            row = self.conn.execute("SELECT * FROM sessions WHERE id=?", (f"{agent}:{native_id}",)).fetchone()
        if row is None:
            return None
        return SessionRecord(
            agent=row["agent"],
            native_id=row["native_id"],
            cwd=row["cwd"] or "",
            title=row["title"] or "",
            summary=row["summary"] or "",
            body=row["body"] or "",
            updated_at=int(row["updated_at"] or 0),
            source_path=row["source_path"] or "",
            content_hash=row["content_hash"] or "",
            turns=[Turn(**t) for t in json.loads(row["turns_json"])],
            limitations=json.loads(row["limitations_json"]),
        )

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        agent: str | None = None,
        since_ms: int | None = None,
        order: str = "rank",
        strategy: str = "naive",
    ) -> list[Hit]:
        fts = _fts_query(query)
        where = ["sessions_fts MATCH ?"]
        args: list[object] = [fts]
        if agent:
            where.append("s.agent = ?")
            args.append(agent)
        if since_ms:
            where.append("s.updated_at >= ?")
            args.append(since_ms)
        order_sql = (
            "s.updated_at DESC"
            if order == "recency"
            else "bm25(sessions_fts, 10.0, 5.0, 1.0) ASC, s.updated_at DESC"
        )
        sql = f"""
            SELECT s.*, bm25(sessions_fts, 10.0, 5.0, 1.0) AS rank
            FROM sessions_fts
            JOIN sessions s ON s.rowid = sessions_fts.rowid
            WHERE {' AND '.join(where)}
            ORDER BY {order_sql}
            LIMIT ?
        """
        args.append(limit)
        try:
            rows = self.conn.execute(sql, args).fetchall()
        except sqlite3.OperationalError as exc:
            raise RuntimeError("Session index query failed; rebuild or diagnose the index") from exc
        hits: list[Hit] = []
        for row in rows:
            text = " ".join(p for p in (row["title"], row["summary"], row["body"]) if p)
            hits.append(
                Hit(
                    agent=row["agent"],
                    native_id=row["native_id"],
                    cwd=row["cwd"] or "",
                    title=row["title"] or "",
                    summary=row["summary"] or "",
                    snippet=snippet(text, query),
                    updated_at=int(row["updated_at"] or 0),
                    source_path=row["source_path"] or "",
                    strategy=strategy,
                    rank=float(row["rank"] or 0),
                )
            )
        return hits

    def embedding_count(self) -> int:
        try:
            row = self.conn.execute("SELECT COUNT(*) AS n FROM embeddings").fetchone()
        except sqlite3.OperationalError:
            return 0
        return int(row["n"])

    def insight_count(self) -> int:
        try:
            row = self.conn.execute("SELECT COUNT(*) AS n FROM insights").fetchone()
        except sqlite3.OperationalError:
            return 0
        return int(row["n"])

    def enrich(self, records: list[SessionRecord], *, agent: str | None = None, commit: bool = True) -> dict[str, int]:
        from .embedder import get_embedder
        from .insights import extract_insights

        embedder = get_embedder()
        if agent:
            self.conn.execute("DELETE FROM embeddings WHERE agent=?", (agent,))
            self.conn.execute("DELETE FROM insights WHERE agent=?", (agent,))
        else:
            self.conn.execute("DELETE FROM embeddings")
            self.conn.execute("DELETE FROM insights")
        emb_rows = []
        ins_rows = []
        for rec in records:
            text = " ".join(p for p in (rec.title, rec.summary) if p) or rec.body[:500]
            vec = embedder.embed(text)
            emb_rows.append((rec.id, rec.agent, embedder.dim, embedder.name, vec))
            for insight in extract_insights(rec):
                ins_rows.append(
                    (
                        insight.id,
                        insight.kind,
                        insight.claim,
                        insight.session_id,
                        insight.agent,
                        insight.cwd,
                        insight.updated_at,
                        insight.confidence,
                        insight.extractor,
                    )
                )
        if emb_rows:
            self.conn.executemany(
                "INSERT OR REPLACE INTO embeddings(id, agent, dim, embedder, vec) VALUES (?, ?, ?, ?, ?)",
                emb_rows,
            )
        if ins_rows:
            self.conn.executemany(
                """
                INSERT OR REPLACE INTO insights(
                  id, kind, claim, session_id, agent, cwd, updated_at, confidence, extractor
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ins_rows,
            )
        self.conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('embedder',?)", (embedder.name,))
        if commit:
            self.conn.commit()
        return {"embeddings": len(emb_rows), "insights": len(ins_rows)}

    def semantic_search(
        self,
        query: str,
        *,
        limit: int = 10,
        agent: str | None = None,
        since_ms: int | None = None,
        last: bool = False,
    ) -> list[Hit]:
        from .embedder import cosine, get_embedder

        if self.embedding_count() == 0:
            return []
        qvec = get_embedder().embed(query)
        sql = "SELECT e.id, e.vec, s.* FROM embeddings e JOIN sessions s ON s.id = e.id"
        args: list[object] = []
        where = []
        if agent:
            where.append("s.agent = ?")
            args.append(agent)
        if since_ms:
            where.append("s.updated_at >= ?")
            args.append(since_ms)
        if where:
            sql += " WHERE " + " AND ".join(where)
        rows = self.conn.execute(sql, args).fetchall()
        scored: list[tuple[float, sqlite3.Row]] = []
        for row in rows:
            score = cosine(qvec, row["vec"])
            if score > 0:
                scored.append((score, row))
        if last:
            scored.sort(key=lambda item: int(item[1]["updated_at"] or 0), reverse=True)
        else:
            scored.sort(key=lambda item: item[0], reverse=True)
        hits = []
        for score, row in scored[:limit]:
            text = " ".join(p for p in (row["title"], row["summary"], row["body"]) if p)
            hits.append(
                Hit(
                    agent=row["agent"],
                    native_id=row["native_id"],
                    cwd=row["cwd"] or "",
                    title=row["title"] or "",
                    summary=row["summary"] or "",
                    snippet=snippet(text, query),
                    updated_at=int(row["updated_at"] or 0),
                    source_path=row["source_path"] or "",
                    strategy="semantic",
                    rank=float(score),
                )
            )
        return hits

    def insight_search(
        self,
        query: str,
        *,
        limit: int = 10,
        agent: str | None = None,
        since_ms: int | None = None,
        last: bool = False,
    ) -> list[Hit]:
        from .insights import expand_query

        if self.insight_count() == 0:
            return []
        queries = expand_query(query)
        seen: set[str] = set()
        hits: list[Hit] = []
        for q in queries:
            fts = _fts_query(q)
            where = ["insights_fts MATCH ?"]
            args: list[object] = [fts]
            if agent:
                where.append("i.agent = ?")
                args.append(agent)
            if since_ms:
                where.append("i.updated_at >= ?")
                args.append(since_ms)
            order_sql = "i.updated_at DESC" if last else "bm25(insights_fts, 10.0, 1.0) ASC, i.updated_at DESC"
            sql = f"""
                SELECT i.*, s.title AS session_title, s.source_path AS source_path, s.summary AS session_summary
                FROM insights_fts
                JOIN insights i ON i.rowid = insights_fts.rowid
                LEFT JOIN sessions s ON s.id = i.session_id
                WHERE {' AND '.join(where)}
                ORDER BY {order_sql}
                LIMIT ?
            """
            args.append(limit)
            try:
                rows = self.conn.execute(sql, args).fetchall()
            except sqlite3.OperationalError:
                continue
            for row in rows:
                sid = row["session_id"]
                native = sid.split(":", 1)[1] if ":" in sid else sid
                key = f"{row['agent']}:{native}"
                if key in seen:
                    continue
                seen.add(key)
                hits.append(
                    Hit(
                        agent=row["agent"],
                        native_id=native,
                        cwd=row["cwd"] or "",
                        title=row["session_title"] or row["claim"],
                        summary=row["session_summary"] or "",
                        snippet=f"{row['kind']}: {row['claim']}",
                        updated_at=int(row["updated_at"] or 0),
                        source_path=row["source_path"] or "",
                        strategy="onto",
                        rank=float(row["confidence"] or 0),
                    )
                )
        if last:
            hits.sort(key=lambda h: h.updated_at, reverse=True)
            return hits[:1]
        return hits[:limit]


def _fts_query(query: str) -> str:
    tokens = [t for t in query.replace("'", " ").split() if t]
    if not tokens:
        return '""'
    quoted = []
    for t in tokens:
        t = t.replace('"', "")
        if not t:
            continue
        quoted.append(f'"{t}"')
    return " AND ".join(quoted) if quoted else '""'
