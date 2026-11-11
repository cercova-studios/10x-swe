PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

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
