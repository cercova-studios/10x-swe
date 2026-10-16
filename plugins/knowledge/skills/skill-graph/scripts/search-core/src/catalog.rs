use anyhow::{Context, Result, anyhow, bail};
use rusqlite::{Connection, OpenFlags, params};
use serde_json::{Value, json};
use std::{
    collections::{HashMap, HashSet},
    path::Path,
};

#[cfg(test)]
use std::{fs, io::Read};

#[cfg(test)]
const MAX_GRAPH_BYTES: u64 = 32 * 1024 * 1024;
const MAX_NODES: usize = 100_000;

fn field<'a>(v: &'a Value, key: &str) -> Result<&'a str> {
    v.get(key)
        .and_then(Value::as_str)
        .ok_or_else(|| anyhow!("missing string field {key}"))
}

fn scoped_id(id: &str) -> Result<()> {
    let parts: Vec<_> = id.split('/').collect();
    if id.len() > 1024
        || parts.len() < 2
        || parts
            .iter()
            .any(|p| p.is_empty() || *p == "." || *p == ".." || p.chars().any(char::is_whitespace))
    {
        bail!("invalid scoped skill ID: {id}");
    }
    Ok(())
}

fn array<'a>(graph: &'a Value, name: &str) -> Result<&'a Vec<Value>> {
    graph
        .get(name)
        .and_then(Value::as_array)
        .ok_or_else(|| anyhow!("missing graph array {name}"))
}

/// Import authoritative graph metadata atomically. No skill bodies are read.
#[cfg(test)]
pub fn refresh(graph: &Path, db: &Path) -> Result<Value> {
    if fs::metadata(graph)?.len() > MAX_GRAPH_BYTES {
        bail!("graph exceeds 32 MiB limit");
    }
    let mut bytes = Vec::new();
    fs::File::open(graph)?
        .take(MAX_GRAPH_BYTES + 1)
        .read_to_end(&mut bytes)?;
    if bytes.len() as u64 > MAX_GRAPH_BYTES {
        bail!("graph exceeds 32 MiB limit");
    }
    let value: Value = serde_json::from_slice(&bytes).context("invalid graph JSON")?;
    refresh_checked(&value, db)
}

/// Import the same graph value whose freshness the caller already verified.
/// This validates catalog structure but never substitutes for freshness checks.
pub fn refresh_checked(value: &Value, db: &Path) -> Result<Value> {
    if value.get("schema").and_then(Value::as_u64) != Some(1) {
        bail!("unsupported graph schema");
    }
    if !array(value, "errors")?.is_empty() {
        bail!("graph contains unresolved errors");
    }
    let nodes = array(value, "nodes")?;
    let aliases = array(value, "aliases")?;
    let edges = array(value, "edges")?;
    if nodes.len() > MAX_NODES || aliases.len() > MAX_NODES || edges.len() > MAX_NODES * 20 {
        bail!("graph exceeds catalog count limits");
    }
    let mut ids = HashSet::new();
    for node in nodes {
        let id = field(node, "id")?;
        scoped_id(id)?;
        if !ids.insert(id) {
            bail!("duplicate skill ID: {id}");
        }
        if field(node, "name")?.trim().is_empty() {
            bail!("empty skill name: {id}");
        }
        field(node, "description")?;
        field(node, "scope")?;
        field(node, "path")?;
        field(node, "sha256")?;
        if !matches!(
            node["kind"].as_str().unwrap_or("skill"),
            "skill" | "workflow"
        ) {
            bail!("unsupported discovery node kind");
        }
    }
    let mut alias_map = HashMap::new();
    for alias in aliases {
        let id = field(alias, "id")?;
        scoped_id(id)?;
        let target = field(alias, "target")?;
        if ids.contains(id) || alias_map.insert(id, target).is_some() {
            bail!("duplicate alias ID: {id}");
        }
    }
    // Graph aliases are direct routes to canonical nodes, not recursive aliases.
    for (id, target) in &alias_map {
        if !ids.contains(target) {
            bail!("alias {id} has unknown canonical target {target}");
        }
    }
    let canonical = |id: &str| -> Result<String> {
        if ids.contains(id) {
            Ok(id.to_owned())
        } else if let Some(target) = alias_map.get(id) {
            Ok((*target).to_owned())
        } else {
            bail!("edge has unknown endpoint: {id}")
        }
    };
    let mut resolved_edges = HashSet::new();
    for edge in edges {
        let relation = field(edge, "relation")?;
        if !matches!(
            relation,
            "uses" | "related" | "references" | "associated_workflow" | "uses_skill"
        ) {
            bail!("unsupported graph edge relation");
        }
        let source = canonical(field(edge, "source")?)?;
        let target = canonical(field(edge, "target")?)?;
        let kind = |id: &str| {
            nodes.iter().find(|n| n["id"] == id).unwrap()["kind"]
                .as_str()
                .unwrap_or("skill")
        };
        if (relation == "associated_workflow"
            && (kind(&source) != "skill" || kind(&target) != "workflow"))
            || (relation == "uses_skill"
                && (kind(&source) != "workflow" || kind(&target) != "skill"))
        {
            bail!("invalid workflow relationship endpoints");
        }
        if !resolved_edges.insert((source, target, relation.to_owned())) {
            bail!("duplicate graph edge");
        }
    }
    if let Some(parent) = db.parent().filter(|p| !p.as_os_str().is_empty()) {
        std::fs::create_dir_all(parent)?;
    }
    let mut connection = Connection::open(db)?;
    connection.pragma_update(None, "foreign_keys", "ON")?;
    let tx = connection.transaction()?;
    tx.execute_batch("DROP TABLE IF EXISTS edges; DROP TABLE IF EXISTS aliases;
        DROP TABLE IF EXISTS skills_fts; DROP TABLE IF EXISTS skills;
        CREATE TABLE skills(id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL,
          scope TEXT NOT NULL, path TEXT NOT NULL, sha256 TEXT NOT NULL, kind TEXT NOT NULL);
        CREATE TABLE aliases(id TEXT PRIMARY KEY, target TEXT NOT NULL REFERENCES skills(id));
        CREATE TABLE edges(source TEXT NOT NULL REFERENCES skills(id), target TEXT NOT NULL REFERENCES skills(id),
          relation TEXT NOT NULL, PRIMARY KEY(source,target,relation));
        CREATE VIRTUAL TABLE skills_fts USING fts5(name, description, id UNINDEXED);")?;
    for node in nodes {
        tx.execute(
            "INSERT INTO skills VALUES (?1,?2,?3,?4,?5,?6,?7)",
            params![
                field(node, "id")?,
                field(node, "name")?,
                field(node, "description")?,
                field(node, "scope")?,
                field(node, "path")?,
                field(node, "sha256")?,
                node["kind"].as_str().unwrap_or("skill")
            ],
        )?;
        tx.execute(
            "INSERT INTO skills_fts(name,description,id) VALUES (?1,?2,?3)",
            params![
                field(node, "name")?,
                field(node, "description")?,
                field(node, "id")?
            ],
        )?;
    }
    for (id, target) in &alias_map {
        tx.execute("INSERT INTO aliases VALUES (?1,?2)", params![id, target])?;
    }
    for (source, target, relation) in &resolved_edges {
        tx.execute(
            "INSERT INTO edges VALUES (?1,?2,?3)",
            params![source, target, relation],
        )?;
    }
    tx.pragma_update(None, "user_version", 3)?;
    tx.commit()?;
    Ok(json!({"nodes":nodes.len(),"aliases":aliases.len(),"edges":resolved_edges.len()}))
}

fn read_db(db: &Path) -> Result<Connection> {
    let conn = Connection::open_with_flags(db, OpenFlags::SQLITE_OPEN_READ_ONLY)
        .context("catalog unavailable; refresh it first")?;
    let version: i64 = conn.pragma_query_value(None, "user_version", |row| row.get(0))?;
    if version != 3 {
        bail!("unsupported catalog schema; refresh it first");
    }
    Ok(conn)
}

fn metadata(row: &rusqlite::Row<'_>) -> rusqlite::Result<Value> {
    Ok(
        json!({"id":row.get::<_,String>(0)?,"name":row.get::<_,String>(1)?,
        "description":row.get::<_,String>(2)?,"scope":row.get::<_,String>(3)?,
        "path":row.get::<_,String>(4)?,"sha256":row.get::<_,String>(5)?,"kind":row.get::<_,String>(6)?}),
    )
}

/// OR literal tokens, never accept user-provided FTS syntax.
pub fn search(db: &Path, query: &str, limit: usize) -> Result<Value> {
    search_scoped(db, query, limit, false)
}

pub fn search_scoped(db: &Path, query: &str, limit: usize, only_global: bool) -> Result<Value> {
    if query.len() > 4096 {
        bail!("search query exceeds 4096 bytes");
    }
    let limit = limit.clamp(1, 20);
    let mut seen = HashSet::new();
    let tokens: Vec<_> = query
        .split(|c: char| !c.is_alphanumeric())
        .filter(|s| !s.is_empty())
        .filter(|s| seen.insert(s.to_lowercase()))
        .collect();
    if tokens.len() > 64 {
        bail!("search query exceeds 64 tokens");
    }
    let conn = read_db(db)?;
    if tokens.is_empty() {
        return Ok(json!({"query":query,"limit":limit,"results":[]}));
    }
    let expression = tokens
        .iter()
        .map(|t| format!("\"{t}\""))
        .collect::<Vec<_>>()
        .join(" OR ");
    let mut stmt = conn.prepare(
        "SELECT s.id,s.name,s.description,s.scope,s.path,s.sha256,s.kind,
        bm25(skills_fts,10.0,1.0,0.0) AS score FROM skills_fts
        JOIN skills s ON s.id=skills_fts.id WHERE skills_fts MATCH ?1 AND (?3 = 0 OR s.scope = 'global')
        ORDER BY score,s.id LIMIT ?2",
    )?;
    let rows = stmt.query_map(params![expression, limit as i64, only_global], |row| {
        let mut v = metadata(row)?;
        v["score"] = json!(row.get::<_, f64>(7)?);
        Ok(v)
    })?;
    let results = rows.collect::<rusqlite::Result<Vec<_>>>()?;
    Ok(json!({"query":query,"limit":limit,"results":results}))
}

fn resolve(conn: &Connection, id: &str) -> Result<String> {
    let mut stmt = conn.prepare(
        "SELECT id FROM skills WHERE id=?1 UNION SELECT target FROM aliases WHERE id=?1",
    )?;
    let exact = stmt
        .query_map([id], |row| row.get::<_, String>(0))?
        .collect::<rusqlite::Result<Vec<_>>>()?;
    if let Some(found) = exact.first() {
        return Ok(found.clone());
    }
    let mut stmt = conn.prepare("SELECT id FROM skills WHERE name=?1 ORDER BY id")?;
    let names = stmt
        .query_map([id], |row| row.get::<_, String>(0))?
        .collect::<rusqlite::Result<Vec<_>>>()?;
    match names.as_slice() {
        [only] => Ok(only.clone()),
        [] => bail!("unknown skill: {id}"),
        _ => bail!("ambiguous skill name {id}; use a scoped ID"),
    }
}

pub fn neighbors(db: &Path, id: &str) -> Result<Value> {
    if id.is_empty() || id.len() > 1024 {
        bail!("invalid skill identifier");
    }
    let conn = read_db(db)?;
    let canonical = resolve(&conn, id)?;
    let list = |sql: &str| -> Result<Vec<Value>> {
        let mut stmt = conn.prepare(sql)?;
        let values = stmt
            .query_map([&canonical], metadata)?
            .collect::<rusqlite::Result<Vec<_>>>()?;
        Ok(values)
    };
    let uses = list(
        "SELECT s.id,s.name,s.description,s.scope,s.path,s.sha256,s.kind FROM edges e JOIN skills s ON s.id=e.target WHERE e.source=?1 AND e.relation='uses' ORDER BY s.id",
    )?;
    let used_by = list(
        "SELECT s.id,s.name,s.description,s.scope,s.path,s.sha256,s.kind FROM edges e JOIN skills s ON s.id=e.source WHERE e.target=?1 AND e.relation='uses' ORDER BY s.id",
    )?;
    let mut stmt = conn.prepare("SELECT id FROM aliases WHERE target=?1 ORDER BY id")?;
    let aliases = stmt
        .query_map([&canonical], |row| row.get::<_, String>(0))?
        .collect::<rusqlite::Result<Vec<_>>>()?;
    let workflows = list(
        "SELECT s.id,s.name,s.description,s.scope,s.path,s.sha256,s.kind FROM edges e JOIN skills s ON s.id=e.target WHERE e.source=?1 AND e.relation='associated_workflow' ORDER BY s.id",
    )?;
    let participants = list(
        "SELECT s.id,s.name,s.description,s.scope,s.path,s.sha256,s.kind FROM edges e JOIN skills s ON s.id=e.target WHERE e.source=?1 AND e.relation='uses_skill' ORDER BY s.id",
    )?;
    Ok(
        json!({"id":canonical,"requested_id":id,"uses":uses,"used_by":used_by,"aliases":aliases,"workflows":workflows,"participants":participants}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicUsize, Ordering};
    static COUNTER: AtomicUsize = AtomicUsize::new(0);
    struct Fixture(std::path::PathBuf);
    impl Fixture {
        fn new() -> Self {
            let p = std::env::temp_dir().join(format!(
                "skill-catalog-{}-{}",
                std::process::id(),
                COUNTER.fetch_add(1, Ordering::Relaxed)
            ));
            fs::create_dir(&p).unwrap();
            Self(p)
        }
        fn graph(&self, value: &Value) -> std::path::PathBuf {
            let p = self.0.join("graph.json");
            fs::write(&p, serde_json::to_vec(value).unwrap()).unwrap();
            p
        }
        fn db(&self) -> std::path::PathBuf {
            self.0.join("catalog.sqlite")
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }
    fn node(id: &str, name: &str, description: &str) -> Value {
        let scope = id.rsplit_once('/').unwrap().0;
        json!({"id":id,"name":name,"scope":scope,"description":description,"path":"/fixture/SKILL.md","sha256":"fixture"})
    }
    fn graph() -> Value {
        json!({"schema":1,"errors":[],"nodes":[node("global/alpha","alpha","video lessons"),node("global/beta","beta","alpha research")],"aliases":[{"id":"project/demo/alpha","target":"global/alpha"}],"edges":[{"source":"global/alpha","target":"global/beta","relation":"uses"}]})
    }
    #[test]
    fn import_search_and_neighbors() {
        let f = Fixture::new();
        let g = f.graph(&graph());
        refresh(&g, &f.db()).unwrap();
        let r = search(&f.db(), "alpha", 20).unwrap();
        assert_eq!(r["results"][0]["id"], "global/alpha");
        let n = neighbors(&f.db(), "project/demo/alpha").unwrap();
        assert_eq!(n["uses"][0]["id"], "global/beta");
        assert_eq!(
            neighbors(&f.db(), "beta").unwrap()["used_by"][0]["id"],
            "global/alpha"
        );
        assert!(r["results"][0].get("body").is_none());
    }
    #[test]
    fn failed_import_preserves_catalog() {
        let f = Fixture::new();
        refresh(&f.graph(&graph()), &f.db()).unwrap();
        let mut bad = graph();
        bad["edges"][0]["target"] = json!("global/missing");
        assert!(refresh(&f.graph(&bad), &f.db()).is_err());
        assert_eq!(
            search(&f.db(), "video", 5).unwrap()["results"]
                .as_array()
                .unwrap()
                .len(),
            1
        );
        bad = graph();
        bad["nodes"][0]["id"] = json!("global/../escape");
        assert!(refresh(&f.graph(&bad), &f.db()).is_err());
    }
    #[test]
    fn metacharacters_negatives_and_limits() {
        let f = Fixture::new();
        refresh(&f.graph(&graph()), &f.db()).unwrap();
        for query in [
            "\" OR *",
            "alpha NEAR(\"beta\")",
            "{} : ()",
            "' ; DROP TABLE skills; --",
        ] {
            search(&f.db(), query, 1000).unwrap();
        }
        assert!(
            search(&f.db(), "Azure", 20).unwrap()["results"]
                .as_array()
                .unwrap()
                .is_empty()
        );
        assert_eq!(search(&f.db(), "alpha", 500).unwrap()["limit"], 20);
        assert!(search(&f.db(), &"x".repeat(4097), 5).is_err());
    }
    #[test]
    fn ambiguous_names_and_bad_aliases_rejected() {
        let f = Fixture::new();
        let mut g = graph();
        g["nodes"]
            .as_array_mut()
            .unwrap()
            .push(node("project/demo/other", "alpha", "different"));
        refresh(&f.graph(&g), &f.db()).unwrap();
        assert!(neighbors(&f.db(), "alpha").is_err());
        g["aliases"][0]["target"] = json!("project/demo/nope");
        assert!(refresh(&f.graph(&g), &f.db()).is_err());
    }

    #[test]
    fn global_filter_applies_before_limit() {
        let f = Fixture::new();
        let mut g = graph();
        g["nodes"].as_array_mut().unwrap().push(node(
            "project/demo/different",
            "alpha",
            "alpha alpha alpha",
        ));
        refresh(&f.graph(&g), &f.db()).unwrap();
        let result = search_scoped(&f.db(), "alpha", 1, true).unwrap();
        assert_eq!(result["results"][0]["scope"], "global");
        assert_eq!(result["results"].as_array().unwrap().len(), 1);
    }

    #[test]
    fn checked_import_uses_verified_value_not_changed_path() {
        let f = Fixture::new();
        let verified = graph();
        let mut replacement = graph();
        replacement["nodes"][0]["description"] = json!("replacement-only-marker");
        f.graph(&replacement);
        refresh_checked(&verified, &f.db()).unwrap();
        assert_eq!(
            search(&f.db(), "video", 5).unwrap()["results"]
                .as_array()
                .unwrap()
                .len(),
            1
        );
        assert!(
            search(&f.db(), "replacement-only-marker", 5).unwrap()["results"]
                .as_array()
                .unwrap()
                .is_empty()
        );
    }
}
