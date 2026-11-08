use crate::{
    embed,
    model::{Hit, Session, Turn},
    text::*,
};
use anyhow::{Context, Result, ensure};
use rusqlite::{Connection, OpenFlags, OptionalExtension, params};
use std::{collections::BTreeMap, os::unix::fs::PermissionsExt, path::Path};

pub struct Store {
    pub conn: Connection,
}
impl Store {
    pub fn open(path: &Path, write: bool) -> Result<Self> {
        if !write {
            ensure!(
                path.is_file(),
                "Session index missing; run session-search index explicitly"
            );
        }
        if write {
            std::fs::create_dir_all(path.parent().unwrap_or(Path::new(".")))?;
        }
        let conn = Connection::open_with_flags(
            path,
            if write {
                OpenFlags::SQLITE_OPEN_READ_WRITE | OpenFlags::SQLITE_OPEN_CREATE
            } else {
                OpenFlags::SQLITE_OPEN_READ_ONLY
            },
        )?;
        conn.busy_timeout(std::time::Duration::from_secs(5))?;
        if write {
            conn.execute_batch(include_str!("schema.sql"))?;
            let columns = conn
                .prepare("PRAGMA table_info(sessions)")?
                .query_map([], |r| r.get::<_, String>(1))?
                .collect::<rusqlite::Result<Vec<_>>>()?;
            for column in ["turns_json", "limitations_json"] {
                if !columns.iter().any(|c| c == column) {
                    conn.execute_batch(&format!(
                        "ALTER TABLE sessions ADD COLUMN {column} TEXT NOT NULL DEFAULT '[]'"
                    ))?;
                }
            }
            std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o600))?;
        } else {
            let columns = conn
                .prepare("PRAGMA table_info(sessions)")?
                .query_map([], |r| r.get::<_, String>(1))?
                .collect::<rusqlite::Result<Vec<_>>>()?;
            ensure!(
                ["turns_json", "limitations_json"]
                    .iter()
                    .all(|name| columns.iter().any(|c| c == name)),
                "Session index needs an upgrade; run session-search index explicitly"
            );
        }
        Ok(Self { conn })
    }
    pub fn count(&self, table: &str) -> Result<i64> {
        ensure!(
            ["sessions", "embeddings", "insights"].contains(&table),
            "Invalid index table"
        );
        Ok(self
            .conn
            .query_row(&format!("SELECT COUNT(*) FROM {table}"), [], |r| r.get(0))?)
    }
    pub fn meta(&self, key: &str) -> Result<Option<String>> {
        Ok(self
            .conn
            .query_row("SELECT value FROM meta WHERE key=?", [key], |r| r.get(0))
            .optional()?)
    }
    pub fn set_meta(&self, key: &str, value: &str) -> Result<()> {
        self.conn.execute(
            "INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)",
            params![key, value],
        )?;
        Ok(())
    }
    pub fn records(&self, agent: Option<&str>) -> Result<Vec<Session>> {
        let mut stmt = self
            .conn
            .prepare("SELECT * FROM sessions WHERE (? IS NULL OR agent=?) ORDER BY rowid")?;
        Ok(stmt
            .query_map(params![agent, agent], session_row)?
            .collect::<rusqlite::Result<_>>()?)
    }
    pub fn get(&self, agent: &str, id: &str) -> Result<Option<Session>> {
        Ok(self
            .conn
            .query_row(
                "SELECT * FROM sessions WHERE id=?",
                [format!("{agent}:{id}")],
                session_row,
            )
            .optional()?)
    }
    pub fn replace(&mut self, agent: &str, records: Vec<Session>) -> Result<usize> {
        let mut unique = BTreeMap::<String, Session>::new();
        let mut order = Vec::new();
        for rec in records {
            let id = rec.id();
            if !unique.contains_key(&id) {
                order.push(id.clone());
            }
            if unique
                .get(&id)
                .is_none_or(|old| rec.updated_at >= old.updated_at)
            {
                unique.insert(id, rec);
            }
        }
        let records = order
            .into_iter()
            .map(|id| unique.remove(&id).unwrap())
            .collect::<Vec<_>>();
        let tx = self.conn.transaction()?;
        for table in ["embeddings", "insights", "sessions"] {
            tx.execute(&format!("DELETE FROM {table} WHERE agent=?"), [agent])?;
        }
        for rec in &records {
            tx.execute("INSERT INTO sessions(id,agent,native_id,cwd,title,summary,body,updated_at,source_path,content_hash,turns_json,limitations_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",params![rec.id(),rec.agent,rec.native_id,rec.cwd,rec.title,rec.summary,rec.body,rec.updated_at,rec.source_path,rec.content_hash,serde_json::to_string(&rec.turns)?,serde_json::to_string(&rec.limitations)?])?;
        }
        if !records.is_empty() {
            enrich(&tx, &records)?;
        }
        tx.commit()?;
        Ok(records.len())
    }
    pub fn enrich(&mut self, agent: Option<&str>) -> Result<(usize, usize, usize)> {
        let records = self.records(agent)?;
        let tx = self.conn.transaction()?;
        for table in ["embeddings", "insights"] {
            tx.execute(
                &format!("DELETE FROM {table} WHERE (? IS NULL OR agent=?)"),
                params![agent, agent],
            )?;
        }
        let cards = enrich(&tx, &records)?;
        tx.commit()?;
        Ok((records.len(), records.len(), cards))
    }
    pub fn lexical(
        &self,
        query: &str,
        agent: Option<&str>,
        since: Option<i64>,
        limit: usize,
        last: bool,
    ) -> Result<Vec<Hit>> {
        let order = if last {
            "s.updated_at DESC"
        } else {
            "bm25(sessions_fts,10.0,5.0,1.0) ASC,s.updated_at DESC"
        };
        let mut stmt=self.conn.prepare(&format!("SELECT s.*,bm25(sessions_fts,10.0,5.0,1.0) AS rank FROM sessions_fts JOIN sessions s ON s.rowid=sessions_fts.rowid WHERE sessions_fts MATCH ? AND (? IS NULL OR s.agent=?) AND (? IS NULL OR s.updated_at>=?) ORDER BY {order} LIMIT ?"))?;
        let rows = stmt
            .query_map(
                params![fts(query), agent, agent, since, since, limit as i64],
                |r| Ok((session_row(r)?, r.get::<_, f64>("rank")?)),
            )?
            .collect::<rusqlite::Result<Vec<_>>>()
            .context("Session index query failed; rebuild or diagnose the index")?;
        Ok(rows
            .into_iter()
            .map(|(s, rank)| hit(&s, query, "naive", rank, None))
            .collect())
    }
    pub fn semantic(
        &self,
        query: &str,
        agent: Option<&str>,
        since: Option<i64>,
        limit: usize,
        last: bool,
    ) -> Result<Vec<Hit>> {
        ensure!(
            self.meta("embedder")?.as_deref() == Some(embed::name()?),
            "Stored embedding model differs; explicitly reindex with the selected model"
        );
        let vector = embed::embed(query)?;
        let mut stmt=self.conn.prepare("SELECT s.*,e.vec FROM embeddings e JOIN sessions s ON s.id=e.id WHERE (? IS NULL OR s.agent=?) AND (? IS NULL OR s.updated_at>=?)")?;
        let rows = stmt
            .query_map(params![agent, agent, since, since], |r| {
                Ok((session_row(r)?, r.get::<_, Vec<u8>>("vec")?))
            })?
            .collect::<rusqlite::Result<Vec<_>>>()?;
        let mut scored = rows
            .into_iter()
            .filter_map(|(s, v)| {
                let score = embed::cosine(&vector, &v);
                (score > 0.0).then(|| hit(&s, query, "semantic", score, None))
            })
            .collect::<Vec<_>>();
        scored.sort_by(|a, b| {
            if last {
                b.updated_at.cmp(&a.updated_at)
            } else {
                b.rank.total_cmp(&a.rank)
            }
        });
        scored.truncate(limit);
        Ok(scored)
    }
    pub fn onto(
        &self,
        query: &str,
        agent: Option<&str>,
        since: Option<i64>,
        limit: usize,
        last: bool,
    ) -> Result<Vec<Hit>> {
        let mut queries = vec![query.to_owned()];
        let lower = squeeze(query).to_lowercase();
        for &(phrase, replacement) in ALIASES {
            if lower.contains(phrase) {
                queries.push(replacement.into())
            }
        }
        let mut hits = Vec::new();
        let mut seen = std::collections::BTreeSet::new();
        for query in queries {
            let order = if last {
                "i.updated_at DESC"
            } else {
                "bm25(insights_fts,10.0,1.0) ASC,i.updated_at DESC"
            };
            let mut stmt=self.conn.prepare(&format!("SELECT s.*,i.claim,i.kind,i.confidence FROM insights_fts JOIN insights i ON i.rowid=insights_fts.rowid LEFT JOIN sessions s ON s.id=i.session_id WHERE insights_fts MATCH ? AND (? IS NULL OR i.agent=?) AND (? IS NULL OR i.updated_at>=?) ORDER BY {order} LIMIT ?"))?;
            let rows = stmt
                .query_map(
                    params![fts(&query), agent, agent, since, since, limit as i64],
                    |r| {
                        Ok((
                            session_row(r)?,
                            r.get::<_, String>("kind")?,
                            r.get::<_, String>("claim")?,
                            r.get::<_, f64>("confidence")?,
                        ))
                    },
                )?
                .collect::<rusqlite::Result<Vec<_>>>()?;
            for (rec, kind, claim, rank) in rows {
                if seen.insert(rec.id()) {
                    hits.push(hit(
                        &rec,
                        &query,
                        "onto",
                        rank,
                        Some(format!("{kind}: {claim}")),
                    ))
                }
            }
        }
        if last {
            hits.sort_by_key(|h| std::cmp::Reverse(h.updated_at));
        }
        hits.truncate(limit);
        Ok(hits)
    }
}
fn session_row(r: &rusqlite::Row<'_>) -> rusqlite::Result<Session> {
    fn decoded<T: serde::de::DeserializeOwned>(
        r: &rusqlite::Row<'_>,
        name: &str,
    ) -> rusqlite::Result<T> {
        let s = r.get::<_, String>(name)?;
        serde_json::from_str(&s).map_err(|e| {
            rusqlite::Error::FromSqlConversionFailure(0, rusqlite::types::Type::Text, Box::new(e))
        })
    }
    Ok(Session {
        agent: r.get("agent")?,
        native_id: r.get("native_id")?,
        cwd: r.get::<_, Option<String>>("cwd")?.unwrap_or_default(),
        title: r.get::<_, Option<String>>("title")?.unwrap_or_default(),
        summary: r.get::<_, Option<String>>("summary")?.unwrap_or_default(),
        body: r.get::<_, Option<String>>("body")?.unwrap_or_default(),
        updated_at: r.get::<_, Option<i64>>("updated_at")?.unwrap_or(0),
        source_path: r
            .get::<_, Option<String>>("source_path")?
            .unwrap_or_default(),
        content_hash: r
            .get::<_, Option<String>>("content_hash")?
            .unwrap_or_default(),
        turns: decoded::<Vec<Turn>>(r, "turns_json")?,
        limitations: decoded::<Vec<String>>(r, "limitations_json")?,
    })
}
fn fts(query: &str) -> String {
    let tokens = query
        .replace('\'', " ")
        .split_whitespace()
        .map(|s| s.replace('"', ""))
        .filter(|s| !s.is_empty())
        .map(|s| format!("\"{s}\""))
        .collect::<Vec<_>>();
    if tokens.is_empty() {
        "\"\"".into()
    } else {
        tokens.join(" AND ")
    }
}
fn hit(s: &Session, query: &str, strategy: &str, rank: f64, selected: Option<String>) -> Hit {
    Hit {
        agent: s.agent.clone(),
        native_id: s.native_id.clone(),
        cwd: s.cwd.clone(),
        title: s.title.clone(),
        summary: s.summary.clone(),
        snippet: selected.unwrap_or_else(|| {
            snippet(
                &[s.title.as_str(), s.summary.as_str(), s.body.as_str()]
                    .into_iter()
                    .filter(|s| !s.is_empty())
                    .collect::<Vec<_>>()
                    .join(" "),
                query,
                240,
            )
        }),
        updated_at: s.updated_at,
        source_path: s.source_path.clone(),
        strategy: strategy.into(),
        rank,
        citations: Vec::new(),
        id: s.id(),
    }
}
fn enrich(conn: &Connection, records: &[Session]) -> Result<usize> {
    static REJECT: std::sync::LazyLock<regex::Regex> = std::sync::LazyLock::new(|| {
        regex::Regex::new(r"(?i)\b(don't|do not|instead of|rejected|not a |avoid|never)\b").unwrap()
    });
    static DECIDE: std::sync::LazyLock<regex::Regex> = std::sync::LazyLock::new(|| {
        regex::Regex::new(r"(?i)\b(locked|we'll use|we will use|decided|v1:|ship)\b").unwrap()
    });
    let mut count = 0;
    let name = embed::name()?;
    for rec in records {
        let text = [rec.title.as_str(), rec.summary.as_str()]
            .into_iter()
            .filter(|s| !s.is_empty())
            .collect::<Vec<_>>()
            .join(" ");
        let text = if text.is_empty() {
            rec.body.chars().take(500).collect()
        } else {
            text
        };
        conn.execute(
            "INSERT OR REPLACE INTO embeddings(id,agent,dim,embedder,vec) VALUES(?,?,?,?,?)",
            params![
                rec.id(),
                rec.agent,
                embed::DIM as i64,
                name,
                embed::embed(&text)?
            ],
        )?;
        let head = clip(
            &title(&[rec.title.clone(), rec.summary.clone(), rec.body.clone()]),
            180,
        );
        if head == "(untitled)" || head.to_lowercase().starts_with("new session") {
            continue;
        }
        let kind = if REJECT.is_match(&head) {
            "rejection"
        } else if DECIDE.is_match(&head) {
            "decision"
        } else {
            "finding"
        };
        let confidence = if kind == "finding" { 0.6 } else { 0.75 };
        let hash = sha(format!("{}:{kind}:{head}", rec.id()));
        let id = format!("{}:{kind}:{}", rec.id(), &hash[..12]);
        conn.execute("INSERT OR REPLACE INTO insights(id,kind,claim,session_id,agent,cwd,updated_at,confidence,extractor) VALUES(?,?,?,?,?,?,?,?,?)",params![id,kind,head,rec.id(),rec.agent,rec.cwd,rec.updated_at,confidence,"heuristic"])?;
        count += 1;
    }
    conn.execute(
        "INSERT OR REPLACE INTO meta(key,value) VALUES('embedder',?)",
        [name],
    )?;
    Ok(count)
}
const ALIASES: &[(&str, &str)] = &[
    ("session analytics", "session-search"),
    ("session-analytics", "session-search"),
    ("conversation history", "session-search"),
    ("conversation search", "session-search"),
    ("gemini", "agy"),
    ("antigravity", "agy"),
    ("cursor-agent", "cursor"),
    ("prime-agent", "prime"),
    ("bm25", "lexical-search"),
    ("bm42", "lexical-search"),
    ("similarity search", "semantic-search"),
    ("embeddings", "semantic-search"),
    ("insight graph", "onto-search"),
    ("ontological", "onto-search"),
];
