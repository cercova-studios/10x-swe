use crate::{model::Session, text::*, turns};
use anyhow::{Context, Result, ensure};
use rusqlite::{Connection, OpenFlags, types::ValueRef};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    io::{Read, Seek},
    os::unix::fs::PermissionsExt,
    path::{Path, PathBuf},
    process::{Command, Stdio},
};
pub const AGENTS: &[&str] = &[
    "claude", "codex", "cursor", "grok", "copilot", "agy", "opencode", "amp", "omp", "prime", "pi",
];
pub const CHOICES: &[&str] = &[
    "agy",
    "amp",
    "antigravity",
    "claude",
    "codex",
    "copilot",
    "cursor",
    "cursor-agent",
    "gemini",
    "grok",
    "omp",
    "opencode",
    "pi",
    "prime",
    "prime-agent",
];
pub fn resolve(agent: &str) -> &str {
    match agent {
        "gemini" | "antigravity" => "agy",
        "cursor-agent" => "cursor",
        "prime-agent" => "prime",
        _ => agent,
    }
}
pub fn home() -> Result<PathBuf> {
    Ok(PathBuf::from(
        std::env::var_os("HOME").context("HOME unavailable")?,
    ))
}
fn walk(root: &Path, suffix: &str) -> Result<Vec<PathBuf>> {
    let mut out = Vec::new();
    if !root.exists() {
        return Ok(out);
    }
    let mut dirs = vec![root.to_owned()];
    while let Some(dir) = dirs.pop() {
        for entry in fs::read_dir(dir)? {
            let entry = entry?;
            let p = entry.path();
            let ty = entry.file_type()?;
            if ty.is_dir() {
                dirs.push(p)
            } else if p.is_file()
                && p.file_name()
                    .is_some_and(|s| s.to_string_lossy().ends_with(suffix))
            {
                out.push(p)
            }
        }
    }
    Ok(out)
}
fn objects(path: &Path) -> Result<impl Iterator<Item = Result<Value>>> {
    let rows = if path.exists() {
        Some(turns::lines(path, false)?)
    } else {
        None
    };
    Ok(rows.into_iter().flatten().map(|row| row.map(|(_, _, v)| v)))
}
fn make(
    agent: &str,
    id: String,
    cwd: String,
    raw_title: String,
    texts: Vec<String>,
    updated: i64,
    source: &Path,
) -> Session {
    let mut parts = vec![raw_title.clone()];
    parts.extend(texts.iter().cloned());
    let title = title(&parts);
    let body = body(&texts);
    let mut rec = Session {
        agent: agent.into(),
        native_id: id,
        cwd,
        title: title.clone(),
        summary: if raw_title.is_empty() {
            title.clone()
        } else {
            raw_title
        },
        body: body.clone(),
        updated_at: updated,
        source_path: source.to_string_lossy().into_owned(),
        ..Default::default()
    };
    rec.content_hash = content_hash(&[&title, &body, &updated.to_string()]);
    rec
}
pub fn crawl(agent: &str) -> Result<Vec<Session>> {
    let home = home()?;
    match agent {
        "codex" => codex(&home),
        "claude" => claude(&home),
        "prime" | "pi" | "omp" => generic(&home, agent),
        "grok" => grok(&home),
        "cursor" | "copilot" | "opencode" => sql_adapter(&home, agent),
        "agy" => agy(&home),
        "amp" => amp(&home),
        _ => anyhow::bail!("Unknown adapter {agent}"),
    }
}
fn codex(home: &Path) -> Result<Vec<Session>> {
    let root = home.join(".codex");
    let idx = root.join("session_index.jsonl");
    let mut index = BTreeMap::new();
    for v in objects(&idx)? {
        let v = v?;
        if !v["id"].is_null() {
            index.insert(string(&v["id"]), v);
        }
    }
    let mut history = BTreeMap::<String, Vec<String>>::new();
    for v in objects(&root.join("history.jsonl"))? {
        let v = v?;
        let id = string(&v["session_id"]);
        let text = flatten(&v["text"], 0);
        if !id.is_empty() && !text.is_empty() {
            history.entry(id).or_default().push(text)
        }
    }
    let mut seen = BTreeSet::new();
    let mut out = Vec::new();
    for path in walk(&root.join("sessions"), ".jsonl")? {
        let stem = path
            .file_stem()
            .unwrap_or_default()
            .to_string_lossy()
            .into_owned();
        seen.insert(
            stem.chars()
                .skip(stem.chars().count().saturating_sub(36))
                .collect::<String>(),
        );
        let mut id = if stem.starts_with("rollout-") && stem.len() > 36 {
            stem[stem.len() - 36..].into()
        } else {
            stem
        };
        let (mut cwd, mut meta_title, mut updated) = (String::new(), String::new(), mtime(&path));
        let mut users = Vec::new();
        let mut guardian = false;
        for v in objects(&path)? {
            let v = v?;
            updated = updated.max(time(&v["timestamp"]));
            let p = &v["payload"];
            if !p.is_object() {
                continue;
            }
            if cwd.is_empty() {
                cwd = string(&p["cwd"])
            }
            if v["type"] == "session_meta" {
                if p["source"]["subagent"]["other"] == "guardian" {
                    guardian = true;
                    break;
                }
                if !p["id"].is_null() {
                    id = string(&p["id"])
                }
                meta_title = flatten(first(p, &["summary", "name"]), 0);
            }
            if p["type"] == "user_message" || p["role"] == "user" {
                let text = flatten(first(p, &["message", "content"]), 0);
                if !text.is_empty() {
                    users.push(text)
                }
            }
        }
        if guardian {
            continue;
        }
        let mut limitations = Vec::new();
        let turns = turns::read(&path, "codex", &mut limitations)?;
        let idx = index.get(&id).unwrap_or(&Value::Null);
        let texts = if !turns.is_empty() {
            turns.iter().map(|t| t.text.clone()).collect()
        } else if !users.is_empty() {
            users
        } else {
            history.get(&id).cloned().unwrap_or_default()
        };
        if texts.is_empty() && idx.is_null() {
            continue;
        }
        updated = updated.max(time(&idx["updated_at"]));
        let mut parts = vec![string(&idx["thread_name"]), meta_title];
        parts.extend(texts.iter().cloned());
        let title = title(&parts);
        let body = if turns.is_empty() {
            body(&texts)
        } else {
            texts.join("\n")
        };
        let summary = if idx["thread_name"].as_str().is_some_and(|s| !s.is_empty()) {
            string(&idx["thread_name"])
        } else {
            title.clone()
        };
        let hash = content_hash(&[&title, &body, &updated.to_string()]);
        seen.insert(id.clone());
        out.push(Session {
            agent: "codex".into(),
            native_id: id,
            cwd,
            title,
            summary,
            body,
            updated_at: updated,
            source_path: path.to_string_lossy().into_owned(),
            content_hash: hash,
            turns,
            limitations,
        });
    }
    for (id, meta) in index {
        if !seen.contains(&id) {
            out.push(make(
                "codex",
                id.clone(),
                String::new(),
                string(&meta["thread_name"]),
                history.get(&id).cloned().unwrap_or_default(),
                time(&meta["updated_at"]),
                &idx,
            ));
        }
    }
    Ok(out)
}
fn claude(home: &Path) -> Result<Vec<Session>> {
    let mut out = Vec::new();
    for path in walk(&home.join(".claude/projects"), ".jsonl")? {
        let (mut id, mut cwd, mut updated) = (
            path.file_stem()
                .unwrap_or_default()
                .to_string_lossy()
                .into_owned(),
            String::new(),
            mtime(&path),
        );
        let mut users = Vec::new();
        for v in objects(&path)? {
            let v = v?;
            let sid = first(&v, &["sessionId", "session_id"]);
            if !sid.is_null() {
                id = string(sid)
            }
            if cwd.is_empty() {
                cwd = string(&v["cwd"])
            }
            updated = updated.max(time(&v["timestamp"]));
            if v["type"] == "user" {
                let text = flatten(first(&v, &["message", "content"]), 0);
                if !text.is_empty() {
                    users.push(text)
                }
            }
        }
        let mut limitations = Vec::new();
        let turns = turns::read(&path, "claude", &mut limitations)?;
        if turns.is_empty() && users.is_empty() && cwd.is_empty() {
            continue;
        }
        let mut rec = make("claude", id, cwd, String::new(), users, updated, &path);
        rec.body = turns
            .iter()
            .map(|t| t.text.as_str())
            .collect::<Vec<_>>()
            .join("\n");
        rec.content_hash = content_hash(&[&rec.title, &rec.body, &updated.to_string()]);
        rec.turns = turns;
        rec.limitations = limitations;
        out.push(rec);
    }
    Ok(out)
}
fn generic(home: &Path, agent: &str) -> Result<Vec<Session>> {
    let mut out = Vec::new();
    let mut seen = BTreeSet::new();
    for path in walk(&home.join(format!(".{agent}/agent/sessions")), ".jsonl")? {
        let (mut id, mut cwd, mut title, mut updated) = (
            path.file_stem()
                .unwrap_or_default()
                .to_string_lossy()
                .into_owned(),
            String::new(),
            String::new(),
            mtime(&path),
        );
        let mut users = Vec::new();
        for v in objects(&path)? {
            let v = v?;
            updated = updated.max(time(first(&v, &["timestamp", "updatedAt"])));
            match v["type"].as_str() {
                Some("session") => {
                    if !v["id"].is_null() {
                        id = string(&v["id"])
                    }
                    if !v["cwd"].is_null() {
                        cwd = string(&v["cwd"])
                    }
                    if title.is_empty() {
                        title = flatten(&v["title"], 0)
                    }
                }
                Some("title" | "title_change") => {
                    let value = flatten(&v["title"], 0);
                    if !value.is_empty() {
                        title = value
                    }
                }
                Some("message") => {
                    let msg = if v["message"].is_object() {
                        &v["message"]
                    } else {
                        &v
                    };
                    if !msg["role"].is_null() && msg["role"] != "user" {
                        continue;
                    }
                    let text = flatten(&msg["content"], 0);
                    if !text.is_empty() {
                        users.push(text)
                    }
                    if users.len() >= 24 {
                        break;
                    }
                }
                _ => {}
            }
        }
        if !users.is_empty() || !title.is_empty() {
            seen.insert(id.clone());
            out.push(make(agent, id, cwd, title, users, updated, &path))
        }
    }
    if agent == "omp" {
        let db = home.join(".omp/agent/history.db");
        if db.exists() {
            let mut titles = BTreeMap::new();
            for v in sql(
                &db,
                "SELECT session_id,title,updated_at FROM session_titles",
            )? {
                titles.insert(string(&v["session_id"]), v);
            }
            let mut groups = BTreeMap::<String, Vec<Value>>::new();
            for v in sql(
                &db,
                "SELECT session_id,prompt,created_at,cwd FROM history ORDER BY id",
            )? {
                let sid = string(first(&v, &["session_id"]));
                groups
                    .entry(if sid.is_empty() {
                        "history".into()
                    } else {
                        sid
                    })
                    .or_default()
                    .push(v)
            }
            for (sid, items) in groups {
                if seen.contains(&sid) {
                    continue;
                }
                let texts = items
                    .iter()
                    .map(|v| flatten(&v["prompt"], 0))
                    .filter(|s| !s.is_empty())
                    .collect();
                let cwd = items
                    .iter()
                    .rev()
                    .map(|v| string(&v["cwd"]))
                    .find(|s| !s.is_empty())
                    .unwrap_or_default();
                let meta = titles.get(&sid).unwrap_or(&Value::Null);
                let updated = items
                    .iter()
                    .map(|v| time(&v["created_at"]))
                    .max()
                    .unwrap_or(0)
                    .max(time(&meta["updated_at"]));
                out.push(make(
                    agent,
                    sid,
                    cwd,
                    flatten(&meta["title"], 0),
                    texts,
                    updated,
                    &db,
                ));
            }
        }
    }
    Ok(out)
}
fn grok(home: &Path) -> Result<Vec<Session>> {
    let mut out = Vec::new();
    for path in walk(&home.join(".grok/sessions"), "summary.json")? {
        if path.file_name().is_none_or(|n| n != "summary.json") {
            continue;
        }
        let folder = path.parent().unwrap();
        let data = read_json(&path).unwrap_or(json!({}));
        let info = &data["info"];
        let id = if info["id"].is_null() {
            folder
                .file_name()
                .unwrap_or_default()
                .to_string_lossy()
                .into_owned()
        } else {
            string(&info["id"])
        };
        let cwd = if info["cwd"].as_str().is_some_and(|s| !s.is_empty()) {
            string(&info["cwd"])
        } else {
            decode(
                &folder
                    .parent()
                    .and_then(|p| p.file_name())
                    .unwrap_or_default()
                    .to_string_lossy(),
            )
        };
        let updated = time(first(&data, &["last_active_at", "updated_at"]));
        let updated = if updated == 0 { mtime(&path) } else { updated };
        let mut users = Vec::new();
        for v in objects(&folder.join("chat_history.jsonl"))? {
            let v = v?;
            if matches!(v["type"].as_str(), Some("user" | "human")) {
                let text = flatten(first(&v, &["content", "message"]), 0);
                if !text.is_empty() {
                    users.push(text)
                }
                if users.len() >= 24 {
                    break;
                }
            }
        }
        let summary = flatten(&data["session_summary"], 0);
        if summary.is_empty() && users.is_empty() {
            continue;
        }
        let mut texts = vec![summary.clone()];
        texts.extend(users);
        out.push(make("grok", id, cwd, summary, texts, updated, folder));
    }
    Ok(out)
}
fn read_json(path: &Path) -> Result<Value> {
    let mut file = fs::File::open(path)?;
    let mut raw = Vec::new();
    file.by_ref()
        .take(64 * 1024 * 1024 + 1)
        .read_to_end(&mut raw)?;
    ensure!(raw.len() <= 64 * 1024 * 1024, "Source JSON exceeds 64 MiB");
    Ok(serde_json::from_slice(&raw)?)
}
fn sql(path: &Path, query: &str) -> Result<Vec<Value>> {
    let conn = Connection::open_with_flags(path, OpenFlags::SQLITE_OPEN_READ_ONLY)?;
    let mut stmt = conn.prepare(query)?;
    let names = stmt
        .column_names()
        .into_iter()
        .map(str::to_owned)
        .collect::<Vec<_>>();
    let rows = stmt
        .query_map([], |r| {
            let mut v = serde_json::Map::new();
            for (i, name) in names.iter().enumerate() {
                let value = match r.get_ref(i)? {
                    ValueRef::Null => Value::Null,
                    ValueRef::Integer(n) => json!(n),
                    ValueRef::Real(n) => json!(n),
                    ValueRef::Text(s) => json!(String::from_utf8_lossy(s)),
                    ValueRef::Blob(s) => json!(String::from_utf8_lossy(s)),
                };
                v.insert(name.clone(), value);
            }
            Ok(Value::Object(v))
        })?
        .collect::<rusqlite::Result<_>>()?;
    Ok(rows)
}
fn sql_adapter(home: &Path, agent: &str) -> Result<Vec<Session>> {
    let mut out = Vec::new();
    match agent {
        "cursor" => {
            let path = home.join(
                "Library/Application Support/Cursor/User/globalStorage/conversation-search.db",
            );
            if !path.exists() {
                return Ok(out);
            }
            for v in sql(
                &path,
                "SELECT c.id,c.title,c.updated_at,f.body FROM conversations c LEFT JOIN conversation_fts f ON f.rowid=c.fts_rowid",
            )? {
                let mut rec = make(
                    agent,
                    string(&v["id"]),
                    String::new(),
                    string(&v["title"]),
                    vec![flatten(&v["body"], 0)],
                    time(&v["updated_at"]),
                    &path,
                );
                if rec.body.is_empty() {
                    rec.body = rec.title.clone()
                }
                out.push(rec);
            }
        }
        "copilot" => {
            let path = home.join(".copilot/session-store.db");
            if !path.exists() {
                return Ok(out);
            }
            let mut turns = BTreeMap::<String, Vec<String>>::new();
            for v in sql(
                &path,
                "SELECT session_id,user_message,timestamp FROM turns ORDER BY turn_index",
            )? {
                let text = flatten(&v["user_message"], 0);
                if !text.is_empty() {
                    turns
                        .entry(string(&v["session_id"]))
                        .or_default()
                        .push(text)
                }
            }
            for v in sql(
                &path,
                "SELECT id,cwd,summary,created_at,updated_at FROM sessions",
            )? {
                let summary = flatten(&v["summary"], 0);
                let mut texts = vec![summary.clone()];
                texts.extend(turns.remove(&string(&v["id"])).unwrap_or_default());
                out.push(make(
                    agent,
                    string(&v["id"]),
                    string(&v["cwd"]),
                    summary,
                    texts,
                    time(first(&v, &["updated_at", "created_at"])),
                    &path,
                ))
            }
        }
        "opencode" => {
            let path = home.join(".local/share/opencode/opencode.db");
            if !path.exists() {
                return Ok(out);
            }
            let mut users = BTreeMap::<String, Vec<String>>::new();
            for v in sql(
                &path,
                "SELECT m.session_id AS session_id,m.data AS mdata,p.data AS pdata FROM message m JOIN part p ON p.message_id=m.id",
            )? {
                let m = serde_json::from_str::<Value>(&string(&v["mdata"])).unwrap_or(Value::Null);
                let p = serde_json::from_str::<Value>(&string(&v["pdata"])).unwrap_or(Value::Null);
                if m["role"] != "user" || !p["type"].is_null() && p["type"] != "text" {
                    continue;
                }
                let text = flatten(&p, 0);
                let text = if text.is_empty() {
                    flatten(&m, 0)
                } else {
                    text
                };
                if !text.is_empty() {
                    users
                        .entry(string(&v["session_id"]))
                        .or_default()
                        .push(text)
                }
            }
            for v in sql(
                &path,
                "SELECT id,title,directory,time_updated,time_created FROM session",
            )? {
                let title = string(&v["title"]);
                let title = if title.to_lowercase().starts_with("new session") {
                    String::new()
                } else {
                    title
                };
                let texts = users.remove(&string(&v["id"])).unwrap_or_default();
                out.push(make(
                    agent,
                    string(&v["id"]),
                    string(&v["directory"]),
                    title,
                    texts,
                    time(first(&v, &["time_updated", "time_created"])),
                    &path,
                ));
            }
        }
        _ => {}
    }
    for rec in &mut out {
        rec.content_hash = content_hash(&[&rec.title, &rec.body, &rec.updated_at.to_string()])
    }
    Ok(out)
}
fn agy(home: &Path) -> Result<Vec<Session>> {
    let mut out = Vec::new();
    let mut seen = BTreeSet::new();
    for rel in [".gemini/antigravity-cli", ".gemini/antigravity"] {
        let root = home.join(rel);
        let path = root.join("history.jsonl");
        let mut groups = BTreeMap::<String, Vec<(i64, String)>>::new();
        for v in objects(&path)? {
            let v = v?;
            let text = flatten(first(&v, &["display", "content"]), 0);
            if text.is_empty() {
                continue;
            }
            let ws = string(first(&v, &["workspace"]));
            groups
                .entry(if ws.is_empty() { "global".into() } else { ws })
                .or_default()
                .push((time(&v["timestamp"]), text));
        }
        for (ws, mut items) in groups {
            let id = format!("history:{ws}");
            if !seen.insert(id.clone()) {
                continue;
            }
            items.sort_by_key(|v| v.0);
            let updated = items
                .iter()
                .map(|v| v.0)
                .max()
                .unwrap_or_else(|| mtime(&path));
            let texts = items.into_iter().map(|v| v.1).collect();
            out.push(make(
                "agy",
                id,
                if ws == "global" { String::new() } else { ws },
                String::new(),
                texts,
                updated,
                &path,
            ));
        }
        let path = root.join("conversation_summaries.db");
        if !path.exists() {
            continue;
        }
        let tables = match sql(&path, "SELECT name FROM sqlite_master WHERE type='table'") {
            Ok(v) => v,
            Err(_) => continue,
        };
        for table in tables {
            let table = string(&table["name"]);
            let quote = |s: &str| format!("\"{}\"", s.replace('"', "\"\""));
            let cols = sql(&path, &format!("PRAGMA table_info({})", quote(&table)))?
                .into_iter()
                .map(|v| string(&v["name"]))
                .collect::<Vec<_>>();
            if !cols.iter().any(|c| {
                ["title", "summary", "text", "content"].contains(&c.to_lowercase().as_str())
            }) {
                continue;
            }
            let choose = |names: &[&str]| {
                cols.iter()
                    .find(|c| names.contains(&c.to_lowercase().as_str()))
                    .cloned()
            };
            let id = choose(&["id", "conversation_id", "session_id"])
                .or_else(|| cols.first().cloned())
                .context("Summary table has no identity")?;
            let title = choose(&["title", "name"]);
            let body = choose(&["summary", "text", "content", "body"]);
            let cwd = choose(&["cwd", "workspace", "directory"]);
            let time_col = cols
                .iter()
                .find(|c| c.to_lowercase().contains("time") || c.to_lowercase().contains("updated"))
                .cloned();
            let rows = match sql(&path, &format!("SELECT * FROM {}", quote(&table))) {
                Ok(v) => v,
                Err(_) => continue,
            };
            for row in rows {
                let native = format!("sum:{}", string(&row[&id]));
                if !seen.insert(native.clone()) {
                    continue;
                }
                let value =
                    |c: &Option<String>| c.as_ref().map(|c| &row[c]).unwrap_or(&Value::Null);
                let mut rec = make(
                    "agy",
                    native,
                    string(value(&cwd)),
                    string(value(&title)),
                    vec![flatten(value(&body), 0)],
                    time(value(&time_col)),
                    &path,
                );
                if rec.body.is_empty() {
                    rec.body = rec.title.clone()
                }
                rec.content_hash =
                    content_hash(&[&rec.title, &rec.body, &rec.updated_at.to_string()]);
                out.push(rec);
            }
        }
    }
    Ok(out)
}
fn executable(name: &str) -> Option<PathBuf> {
    std::env::split_paths(&std::env::var_os("PATH")?)
        .map(|p| p.join(name))
        .find(|p| {
            p.is_file()
                && p.metadata()
                    .is_ok_and(|m| m.permissions().mode() & 0o111 != 0)
        })
}
fn amp_json(binary: &Path, args: &[String], timeout: u64) -> Option<Value> {
    let mut stdout = tempfile::tempfile().ok()?;
    let mut child = Command::new(binary)
        .args(args)
        .stdin(Stdio::null())
        .stdout(stdout.try_clone().ok()?)
        .stderr(Stdio::null())
        .spawn()
        .ok()?;
    let start = std::time::Instant::now();
    loop {
        if start.elapsed() > std::time::Duration::from_secs(timeout)
            || stdout.metadata().ok()?.len() > 64 * 1024 * 1024
        {
            let _ = child.kill();
            let _ = child.wait();
            return None;
        }
        if let Some(status) = child.try_wait().ok()? {
            if !status.success() {
                return None;
            }
            break;
        }
        std::thread::sleep(std::time::Duration::from_millis(20));
    }
    stdout.rewind().ok()?;
    let mut bytes = Vec::new();
    stdout
        .take(64 * 1024 * 1024 + 1)
        .read_to_end(&mut bytes)
        .ok()?;
    if bytes.len() > 64 * 1024 * 1024 {
        return None;
    }
    serde_json::from_slice(&bytes).ok()
}
fn file_url(s: &str) -> String {
    if s.starts_with("file://") {
        url::Url::parse(s)
            .map(|u| percent_decode(u.path()))
            .unwrap_or_default()
    } else {
        s.into()
    }
}
fn amp(home: &Path) -> Result<Vec<Session>> {
    let mut out = Vec::new();
    let limit = std::env::var("SESSION_SEARCH_AMP_LIMIT")
        .unwrap_or_else(|_| "200".into())
        .parse::<usize>()?;
    ensure!(limit <= 10000, "Amp thread limit exceeds 10000");
    let timeout = std::env::var("SESSION_SEARCH_AMP_EXPORT_TIMEOUT")
        .unwrap_or_else(|_| "30".into())
        .parse::<u64>()?;
    if let Some(binary) = executable("amp") {
        let mut metas = Vec::new();
        let mut offset = 0;
        while offset < limit {
            let args = [
                "threads",
                "list",
                "--json",
                "--include-archived",
                "--limit",
                "50",
                "--offset",
            ]
            .map(str::to_owned)
            .into_iter()
            .chain([offset.to_string()])
            .collect::<Vec<_>>();
            let Some(Value::Array(rows)) = amp_json(&binary, &args, 20) else {
                break;
            };
            let n = rows.len();
            metas.extend(rows.into_iter().filter(Value::is_object));
            if n < 50 {
                break;
            }
            offset += 50;
        }
        for meta in metas.into_iter().take(limit) {
            let id = string(&meta["id"]);
            if id.is_empty() {
                continue;
            }
            let exported = amp_json(
                &binary,
                &["threads".into(), "export".into(), id.clone()],
                timeout,
            )
            .unwrap_or(Value::Null);
            let title = flatten(
                if exported["title"].as_str().is_some_and(|s| !s.is_empty()) {
                    &exported["title"]
                } else {
                    &meta["title"]
                },
                0,
            );
            let cwd = file_url(&string(&exported["env"]["initial"]["workingDirectory"]));
            let cwd = if cwd.is_empty() {
                file_url(&string(&meta["tree"]))
            } else {
                cwd
            };
            let mut users = Vec::new();
            if let Some(messages) = exported["messages"].as_array() {
                for msg in messages {
                    if matches!(msg["role"].as_str(), Some("user" | "human")) {
                        let text = flatten(&msg["content"], 0);
                        if !text.is_empty() {
                            users.push(text)
                        }
                        if users.len() >= 24 {
                            break;
                        }
                    }
                }
            }
            if users.is_empty() && title.is_empty() {
                continue;
            }
            let updated = time(first(&exported, &["updatedAt", "created"]));
            let updated = if updated == 0 {
                time(&meta["updated"])
            } else {
                updated
            };
            out.push(make(
                "amp",
                id.clone(),
                cwd,
                title,
                users,
                updated,
                Path::new(&format!("amp://threads/{id}")),
            ));
        }
    }
    if !out.is_empty() {
        return Ok(out);
    }
    let path = home.join(".local/share/amp/history.jsonl");
    for (i, v) in objects(&path)?.enumerate() {
        let v = v?;
        let text = flatten(first(&v, &["text", "prompt"]), 0);
        if text.is_empty() {
            continue;
        }
        let id = if v["id"].is_null() {
            format!("history:{i}")
        } else {
            string(&v["id"])
        };
        let updated = time(first(&v, &["ts", "timestamp", "createdAt"]));
        out.push(make(
            "amp",
            id,
            string(&v["cwd"]),
            String::new(),
            vec![text],
            if updated == 0 { mtime(&path) } else { updated },
            &path,
        ));
    }
    Ok(out)
}
