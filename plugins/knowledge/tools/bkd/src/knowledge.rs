//! Domain-neutral knowledge snapshots supplied by the caller; no companion-tool I/O.
#[cfg(test)]
#[path = "knowledge_tests.rs"]
mod tests;
use crate::{
    graph,
    graph::{Edge, Graph, Node},
    index,
    model::{self, hash},
    search, state,
};
use anyhow::{Result, ensure};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    io::Read,
    path::Path,
};

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Packet {
    schema: String,
    corpus: String,
    query: Option<String>,
    nodes: Vec<Node>,
    edges: Vec<Edge>,
    versions: BTreeMap<String, String>,
    hits: Vec<Hit>,
}
#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Hit {
    id: String,
    rank: usize,
    method: String,
    matched_by: Vec<String>,
}
#[derive(Clone, Default)]
pub struct Config {
    packets: Vec<Packet>,
}
impl Config {
    pub fn enabled(&self) -> bool {
        !self.packets.is_empty()
    }
    pub fn read(input: impl Read) -> Result<Self> {
        let mut raw = Vec::new();
        input.take(32 * 1024 * 1024 + 1).read_to_end(&mut raw)?;
        ensure!(
            raw.len() <= 32 * 1024 * 1024,
            "Knowledge input exceeds 32 MiB"
        );
        let mut packets = Vec::new();
        let mut corpora = BTreeSet::new();
        for line in std::str::from_utf8(&raw)?
            .lines()
            .filter(|s| !s.trim().is_empty())
        {
            ensure!(
                line.len() <= 16 * 1024 * 1024,
                "Knowledge record exceeds 16 MiB"
            );
            let p: Packet = serde_json::from_str(line)?;
            ensure!(
                (p.schema == "knowledge-snapshot/v1"
                    || (p.schema == "knowledge-snapshot/v2" && p.corpus == "skills"))
                    && ["insights", "skills", "sessions"].contains(&p.corpus.as_str())
                    && corpora.insert(p.corpus.clone()),
                "Unsupported or duplicate knowledge corpus"
            );
            ensure!(
                p.nodes.len() <= 10000 && p.edges.len() <= 100000 && p.hits.len() <= 100,
                "Knowledge counts exceed limits"
            );
            ensure!(
                p.query.as_ref().is_none_or(|s| !s.trim().is_empty()
                    && s.len() <= 400
                    && model::valid_text(s, 400)),
                "Invalid knowledge query"
            );
            ensure!(
                p.query.is_some() || p.hits.is_empty(),
                "Hits require an explicit query"
            );
            let mut ids = BTreeSet::new();
            for n in &p.nodes {
                let valid = if p.corpus == "insights" {
                    (n.kind == "source_entry"
                        && n.id.strip_prefix("entry:").is_some_and(|s| hex(s, 24)))
                        || (n.kind == "insight"
                            && n.id.strip_prefix("insight:").is_some_and(|s| {
                                s.split_once(':').is_some_and(|(entry, number)| {
                                    hex(entry, 24)
                                        && number
                                            .parse::<usize>()
                                            .is_ok_and(|n| (1..=1000).contains(&n))
                                        && !number.starts_with('0')
                                })
                            }))
                } else if p.corpus == "sessions" {
                    ["session", "session_turn"].contains(&n.kind.as_str())
                        && n.id.starts_with(if n.kind == "session" {
                            "session:"
                        } else {
                            "turn:"
                        })
                        && n.id.split(':').count() >= if n.kind == "session" { 3 } else { 4 }
                        && n.id.split(':').all(|part| !part.is_empty())
                        && model::valid_text(&n.id, 1024)
                } else {
                    (n.kind == "skill"
                        || (p.schema == "knowledge-snapshot/v2" && n.kind == "workflow"))
                        && n.id
                            .strip_prefix(if n.kind == "workflow" {
                                "workflow:"
                            } else {
                                "skill:"
                            })
                            .is_some_and(|s| s.contains('/') && model::valid_text(s, 512))
                };
                ensure!(
                    valid
                        && ids.insert(n.id.clone())
                        && model::valid_text(&n.label, 65536)
                        && n.bookmark_kind.is_none()
                        && n.details.as_ref().is_some_and(Value::is_object),
                    "Invalid knowledge node"
                );
                if let Some(url) = &n.url {
                    ensure!(model::validate_url(url)? == *url, "Invalid source URL");
                }
                ensure!(
                    p.versions.get(&n.id).is_some_and(|v| hex(v, 64)),
                    "Missing node revision"
                );
                let detail = n.details.as_ref().unwrap();
                ensure!(
                    if p.corpus != "skills" {
                        detail["version"].as_str() == p.versions.get(&n.id).map(String::as_str)
                            && detail["coverage"].is_object()
                    } else {
                        detail["sha256"].as_str() == p.versions.get(&n.id).map(String::as_str)
                    },
                    "Node revision or coverage differs"
                );
                if n.kind == "session_turn" {
                    let quote = detail["quote"].as_str().unwrap_or("");
                    let parent = format!(
                        "session:{}:{}",
                        detail["agent"].as_str().unwrap_or(""),
                        detail["session_id"].as_str().unwrap_or("")
                    );
                    ensure!(
                        !quote.is_empty()
                            && quote.chars().count() <= 2000
                            && detail["excerpt_sha256"].as_str()
                                == Some(hash(quote.as_bytes()).as_str())
                            && detail["record_sha256"].as_str()
                                == p.versions.get(&n.id).map(String::as_str)
                            && ["user", "assistant", "tool"]
                                .contains(&detail["role"].as_str().unwrap_or(""))
                            && detail["jsonl_line"].as_u64().is_some_and(|v| v > 0)
                            && n.id
                                == format!(
                                    "turn:{}:{}:{}",
                                    detail["agent"].as_str().unwrap_or(""),
                                    detail["session_id"].as_str().unwrap_or(""),
                                    detail["jsonl_line"]
                                )
                            && detail["char_start"]
                                .as_u64()
                                .is_some_and(|start| detail["char_end"].as_u64()
                                    == start.checked_add(quote.chars().count() as u64))
                            && detail["redacted"].is_boolean()
                            && detail["source_path"]
                                .as_str()
                                .is_some_and(|s| s.len() <= 4096)
                            && detail["json_pointer"]
                                .as_str()
                                .is_some_and(|s| s.starts_with("$."))
                            && detail["session_revision"].as_str()
                                == p.versions.get(&parent).map(String::as_str),
                        "Invalid session citation"
                    );
                    for field in [
                        "record_sha256",
                        "original_text_sha256",
                        "indexed_text_sha256",
                    ] {
                        ensure!(
                            detail[field].as_str().is_some_and(|v| hex(v, 64)),
                            "Invalid session hash"
                        );
                    }
                }
                if n.kind == "insight" {
                    ensure!(
                        detail["evidence"].as_array().is_some_and(|a| !a.is_empty())
                            && ["source-claim", "inference"]
                                .contains(&detail["status"].as_str().unwrap_or("")),
                        "Insight lacks citations or status"
                    );
                }
            }
            ensure!(p.versions.len() == ids.len(), "Unresolved node revisions");
            let mut edges = BTreeSet::new();
            for e in &p.edges {
                ensure!(
                    ids.contains(&e.a)
                        && ids.contains(&e.b)
                        && model::valid_text(&e.kind, 100)
                        && !e.kind.is_empty()
                        && ["recorded", "inferred", "declared", "observed", "reviewed"]
                            .contains(&e.status.as_str())
                        && edges.insert((&e.a, &e.b, &e.kind, &e.status)),
                    "Invalid or unresolved knowledge edge"
                );
                ensure!(
                    if p.corpus == "insights" {
                        e.kind == "derived_from"
                            && e.a.starts_with("insight:")
                            && e.b.starts_with("entry:")
                            && e.status == "recorded"
                    } else if p.corpus == "sessions" {
                        e.kind == "part_of"
                            && e.a.starts_with("turn:")
                            && e.b.starts_with("session:")
                            && e.status == "recorded"
                            && format!(
                                "session:{}",
                                e.a.strip_prefix("turn:")
                                    .unwrap()
                                    .rsplit_once(':')
                                    .unwrap()
                                    .0
                            ) == e.b
                    } else {
                        e.kind.starts_with("skill_")
                    },
                    "Invalid corpus relationship"
                );
                if p.corpus == "insights" {
                    ensure!(
                        e.a.split(':').nth(1) == e.b.split(':').nth(1),
                        "Insight relationship targets another source"
                    );
                }
            }
            if p.corpus == "sessions" {
                let members = p.edges.iter().map(|e| &e.a).collect::<BTreeSet<_>>();
                for n in p.nodes.iter().filter(|n| n.kind == "session_turn") {
                    ensure!(
                        members.contains(&n.id),
                        "Session turn lacks recorded membership"
                    );
                }
            }
            let mut hits = BTreeSet::new();
            for (rank, h) in p.hits.iter().enumerate() {
                ensure!(
                    ids.contains(&h.id)
                        && hits.insert(&h.id)
                        && h.rank == rank + 1
                        && !h.method.is_empty()
                        && model::valid_text(&h.method, 100)
                        && h.matched_by.len() <= 16
                        && h.matched_by.iter().all(|s| model::valid_text(s, 100)),
                    "Invalid ranked hit"
                );
                ensure!(
                    if p.corpus == "insights" {
                        h.id.starts_with("insight:")
                    } else if p.corpus == "sessions" {
                        h.id.starts_with("session:")
                    } else {
                        h.id.starts_with("skill:")
                            || (p.schema == "knowledge-snapshot/v2"
                                && h.id.starts_with("workflow:"))
                    },
                    "Invalid hit corpus"
                );
            }
            packets.push(p);
        }
        ensure!(!packets.is_empty(), "No knowledge snapshots received");
        Ok(Self { packets })
    }
}
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Link {
    kind: String,
    a: String,
    b: String,
    a_version: String,
    b_version: String,
    reason: String,
    reviewed_at: String,
}
#[derive(Default, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Links {
    schema: u32,
    links: Vec<Link>,
}
pub struct Snapshot {
    pub nodes: BTreeMap<String, Node>,
    edges: Vec<Edge>,
    urls: BTreeMap<String, Vec<String>>,
    versions: BTreeMap<String, String>,
    reviewed_links: Vec<Link>,
    pub status: Value,
}
fn hex(s: &str, length: usize) -> bool {
    s.len() == length
        && s.bytes()
            .all(|c| c.is_ascii_hexdigit() && !c.is_ascii_uppercase())
}
fn links(home: &Path) -> Result<Links> {
    let p = home.join("knowledge-links.json");
    if !p.exists() {
        return Ok(Links {
            schema: 1,
            links: Vec::new(),
        });
    }
    let meta = fs::symlink_metadata(&p)?;
    ensure!(
        meta.is_file() && !meta.file_type().is_symlink() && meta.len() <= 16 * 1024 * 1024,
        "Invalid reviewed-link file"
    );
    let mut raw = Vec::new();
    fs::File::open(&p)?
        .take(16 * 1024 * 1024 + 1)
        .read_to_end(&mut raw)?;
    ensure!(raw.len() <= 16 * 1024 * 1024, "Reviewed links exceed limit");
    let l: Links = serde_json::from_slice(&raw)?;
    ensure!(
        l.schema == 1 && l.links.len() <= 10000,
        "Invalid reviewed links"
    );
    let mut seen = BTreeSet::new();
    for link in &l.links {
        ensure!(
            ["references", "inspected_version"].contains(&link.kind.as_str())
                && hex(&link.a_version, 64)
                && hex(&link.b_version, 64)
                && model::valid_text(&link.reason, 1024)
                && !link.reason.trim().is_empty()
                && model::valid_text(&link.reviewed_at, 100)
                && seen.insert((&link.kind, &link.a, &link.b)),
            "Invalid reviewed link"
        );
    }
    Ok(l)
}
impl Snapshot {
    pub fn load(home: &Path, cfg: &Config) -> Result<Self> {
        let mut s = Self {
            nodes: BTreeMap::new(),
            edges: Vec::new(),
            urls: BTreeMap::new(),
            versions: BTreeMap::new(),
            reviewed_links: links(home)?.links,
            status: Value::Null,
        };
        for p in &cfg.packets {
            for n in &p.nodes {
                if n.kind == "source_entry" {
                    if let Some(url) = &n.url {
                        s.urls.entry(url.clone()).or_default().push(n.id.clone());
                    }
                    if let Some(url) = n
                        .details
                        .as_ref()
                        .and_then(|d| d["request_url"].as_str())
                        .and_then(|u| model::validate_url(u).ok())
                    {
                        let ids = s.urls.entry(url).or_default();
                        if !ids.contains(&n.id) {
                            ids.push(n.id.clone());
                        }
                    }
                }
                ensure!(
                    s.nodes.insert(n.id.clone(), n.clone()).is_none(),
                    "Duplicate knowledge node"
                );
            }
            s.versions.extend(p.versions.clone());
            s.edges.extend(p.edges.clone());
        }
        for n in s.nodes.values().filter(|n| n.kind == "source_entry") {
            if let Some(turns) = n
                .details
                .as_ref()
                .and_then(|d| d["session_provenance"]["turns"].as_array())
            {
                for turn in turns {
                    if let Some(id) = turn["id"].as_str()
                        && s.versions.get(id).map(String::as_str) == turn["version"].as_str()
                        && s.nodes.get(id).is_some_and(|n| n.kind == "session_turn")
                    {
                        s.edges.push(Edge {
                            a: n.id.clone(),
                            b: id.into(),
                            kind: "captured_from".into(),
                            status: "recorded".into(),
                            evidence: turn.clone(),
                        });
                    }
                }
            }
        }
        s.status = json!({"corpora":cfg.packets.iter().map(|p|&p.corpus).collect::<Vec<_>>(),"snapshot":hash(serde_json::to_vec(&(&cfg.packets,&s.reviewed_links))?),"integrity":"Caller-supplied snapshots; producer revisions and recorded coverage are not independent verification. No foreign path is read or executed.","stale_links":[]});
        for link in s
            .reviewed_links
            .clone()
            .into_iter()
            .filter(|l| l.kind == "references")
        {
            if s.versions.get(&link.a) == Some(&link.a_version)
                && s.versions.get(&link.b) == Some(&link.b_version)
            {
                s.edges.push(Edge{a:link.a,b:link.b,kind:link.kind,status:"reviewed".into(),evidence:json!({"reason":link.reason,"reviewed_at":link.reviewed_at,"a_version":link.a_version,"b_version":link.b_version})});
            } else {
                s.status["stale_links"]
                    .as_array_mut()
                    .unwrap()
                    .push(serde_json::to_value(link)?);
            }
        }
        Ok(s)
    }
    pub fn enrich(&self, _home: &Path, mut graph: Graph) -> Result<Graph> {
        let mut edges = self.edges.clone();
        for node in &graph.nodes {
            if node.kind != "bookmark" {
                continue;
            }
            if let Some(entries) = node.url.as_ref().and_then(|u| self.urls.get(u)) {
                for entry in entries {
                    edges.push(Edge{a:node.id.clone(),b:entry.clone(),kind:"inspected_version".into(),status:"recorded".into(),evidence:json!({"method":"exact exported source/request URL","version":self.versions[entry],"meaning":"This saved URL has an inspected snapshot; its live contents may have changed."})});
                }
            }
        }
        let ids: BTreeSet<_> = graph
            .nodes
            .iter()
            .filter(|n| n.kind == "bookmark")
            .map(|n| n.id.clone())
            .collect();
        let mut status = self.status.clone();
        for l in self
            .reviewed_links
            .clone()
            .into_iter()
            .filter(|l| l.kind == "inspected_version")
        {
            if !ids.contains(&l.a) {
                continue;
            }
            if l.a_version == l.a && self.versions.get(&l.b) == Some(&l.b_version) {
                edges.push(Edge{a:l.a,b:l.b,kind:l.kind,status:"reviewed".into(),evidence:json!({"reason":l.reason,"version":l.b_version,"reviewed_at":l.reviewed_at})});
            } else {
                status["stale_links"]
                    .as_array_mut()
                    .unwrap()
                    .push(serde_json::to_value(l)?);
            }
        }
        for n in graph.nodes.iter_mut().filter(|n| n.kind == "bookmark") {
            let entries = edges
                .iter()
                .filter(|e| e.a == n.id && e.kind == "inspected_version")
                .map(|e| e.b.as_str())
                .collect::<BTreeSet<_>>();
            n.details = Some(
                json!({"inspection":if entries.is_empty(){"No linked inspection"}else{"Inspected snapshots linked; live source may differ"},"inspected_sources":entries.into_iter().map(|id|&self.nodes[id]).collect::<Vec<_>>()}),
            );
        }
        graph.nodes.extend(self.nodes.values().cloned());
        graph.edges.extend(edges);
        graph.knowledge = Some(status);
        Ok(graph)
    }
    pub fn detail(&self, graph: &Graph, id: &str) -> Result<Value> {
        let n = graph
            .nodes
            .iter()
            .find(|n| n.id == id)
            .ok_or_else(|| anyhow::anyhow!("Unknown entity {id}"))?;
        let adjacent = graph
            .adjacent(id)
            .into_iter()
            .map(|(id, e)| json!({"edge":e,"node":graph.nodes.iter().find(|n|n.id==id)}))
            .collect::<Vec<_>>();
        Ok(
            json!({"node":n,"relationships":adjacent,"knowledge":graph.knowledge,"generation":graph.generation}),
        )
    }
    pub fn inspect(
        &self,
        db: &mut rusqlite::Connection,
        home: &Path,
        filter: &search::Filter,
        id: &str,
    ) -> Result<Value> {
        let tx = db.transaction()?;
        let books = filter.books(&tx)?;
        // Knowledge neighbors need exact URL joins, not bookmark similarity or tag hubs.
        let graph = if self.nodes.contains_key(id) {
            graph::bookmarks(index::revision(&tx)?, &books)
        } else {
            graph::derive(&tx, &books, true)?
        };
        tx.rollback()?;
        self.detail(&self.enrich(home, graph)?, id)
    }
    pub fn review_link(
        &self,
        home: &Path,
        a: &str,
        b: &str,
        reason: &str,
        remove: bool,
        approved: bool,
    ) -> Result<Value> {
        let kind = if a.starts_with("skill:") && b.starts_with("insight:") {
            "references"
        } else if hex(a, 64) && b.starts_with("entry:") {
            "inspected_version"
        } else {
            anyhow::bail!(
                "Use skill:SCOPED_ID → insight:ENTRY:NUMBER, or BOOKMARK_ID → entry:ENTRY"
            );
        };
        let a_version = if remove {
            String::new()
        } else if kind == "references" {
            self.versions
                .get(a)
                .ok_or_else(|| anyhow::anyhow!("Unknown skill"))?
                .clone()
        } else {
            a.into()
        };
        let b_version = if remove {
            String::new()
        } else {
            self.versions
                .get(b)
                .ok_or_else(|| anyhow::anyhow!("Unknown insight endpoint"))?
                .clone()
        };
        ensure!(
            remove || approved && model::valid_text(reason, 1024) && !reason.trim().is_empty(),
            "Read both endpoints, then pass --reviewed and --reason to record this link"
        );
        let mut db = state::db(home)?;
        let tx = db.transaction_with_behavior(rusqlite::TransactionBehavior::Immediate)?;
        let mut l = links(home)?;
        ensure!(
            serde_json::to_vec(&l.links)? == serde_json::to_vec(&self.reviewed_links)?,
            "Reviewed links changed before link review; retry"
        );
        l.links
            .retain(|l| !(l.kind == kind && l.a == a && l.b == b));
        if !remove {
            l.links.push(Link {
                kind: kind.into(),
                a: a.into(),
                b: b.into(),
                a_version,
                b_version,
                reason: reason.into(),
                reviewed_at: std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)?
                    .as_secs()
                    .to_string(),
            });
        }
        ensure!(l.links.len() <= 10000, "Too many reviewed links");
        state::write_json(&home.join("knowledge-links.json"), &l)?;
        tx.commit()?;
        Ok(json!({"a":a,"b":b,"kind":kind,"removed":remove,"local":true,"public":false}))
    }
}

pub fn search(snapshot: &Snapshot, cfg: &Config, query: &str, limit: usize) -> Result<Value> {
    ensure!(
        !query.trim().is_empty() && query.len() <= 400 && (1..=100).contains(&limit),
        "Combined search requires 1–400 query bytes and limit 1–100"
    );
    let mut result = json!({"insights":[],"skills":[],"sessions":[],"knowledge":snapshot.status,"ranking":"Separate producer ranks; linked context is not an additional relevance vote or authority."});
    for p in &cfg.packets {
        // A snapshot for another query remains graph data, never a fresh ranked result.
        let local;
        let hits = if p.query.as_deref() == Some(query) {
            &p.hits
        } else {
            let query = crate::lexical::terms(query);
            let mut rows = Vec::new();
            for n in &p.nodes {
                if ["source_entry", "session_turn"].contains(&n.kind.as_str()) {
                    continue;
                }
                let label = crate::lexical::terms(&n.label);
                let d = n.details.as_ref().unwrap();
                let body = [
                    "title",
                    "description",
                    "claim",
                    "summary",
                    "application",
                    "caveats",
                ]
                .iter()
                .filter_map(|k| d[k].as_str())
                .collect::<Vec<_>>()
                .join(" ");
                let terms = crate::lexical::terms(&body);
                let score = query
                    .iter()
                    .map(|t| usize::from(label.contains(t)) * 3 + usize::from(terms.contains(t)))
                    .sum::<usize>();
                if score > 0 {
                    rows.push((score, n.id.clone()));
                }
            }
            rows.sort_by(|a, b| b.0.cmp(&a.0).then(a.1.cmp(&b.1)));
            local = rows
                .into_iter()
                .take(limit)
                .enumerate()
                .map(|(rank, (_, id))| Hit {
                    id,
                    rank: rank + 1,
                    method: "snapshot lexical".into(),
                    matched_by: vec!["lexical".into()],
                })
                .collect::<Vec<_>>();
            &local
        };
        for hit in hits.iter().take(limit) {
            result[&p.corpus].as_array_mut().unwrap().push(json!({"rank":hit.rank,"node":snapshot.nodes[&hit.id],"method":hit.method,"matched_by":hit.matched_by}));
        }
    }
    result["knowledge"]["query_scope"]=json!(cfg.packets.iter().map(|p|json!({"corpus":p.corpus,"query":p.query,"used_ranks":p.query.as_deref()==Some(query)})).collect::<Vec<_>>());
    Ok(result)
}

pub fn contextualize(
    value: &mut Value,
    graph: &Graph,
    bookmark_ids: &BTreeSet<String>,
    limit: usize,
) {
    let direct_skills = value["skills"]
        .as_array()
        .unwrap()
        .iter()
        .filter_map(|r| r["node"]["id"].as_str().map(str::to_owned))
        .collect::<BTreeSet<_>>();
    let mut insight_ids = value["insights"]
        .as_array()
        .unwrap()
        .iter()
        .filter_map(|r| r["node"]["id"].as_str().map(str::to_owned))
        .collect::<BTreeSet<_>>();
    let entries = graph
        .edges
        .iter()
        .filter(|e| e.kind == "inspected_version" && bookmark_ids.contains(&e.a))
        .map(|e| e.b.clone())
        .collect::<BTreeSet<_>>();
    let mut candidates = BTreeMap::new();
    for e in &graph.edges {
        if e.kind == "derived_from" && entries.contains(&e.b) {
            candidates.insert(e.a.clone(), ("inspected source link", e.b.clone()));
        }
        if e.kind == "references" && e.status == "reviewed" && direct_skills.contains(&e.a) {
            candidates.insert(e.b.clone(), ("reviewed skill link", e.a.clone()));
        }
    }
    let mut omitted = 0;
    for (id, (method, via)) in candidates {
        if insight_ids.contains(&id) {
            continue;
        }
        let rows = value["insights"].as_array_mut().unwrap();
        if rows.len() >= limit {
            omitted += 1;
            continue;
        }
        if let Some(node) = graph.nodes.iter().find(|n| n.id == id) {
            rows.push(json!({"rank":rows.len()+1,"node":node,"method":method,"via":via}));
            insight_ids.insert(id);
        }
    }
    let mut skill_ids = direct_skills;
    let mut omitted_skills = 0;
    for e in &graph.edges {
        if e.kind != "references"
            || e.status != "reviewed"
            || !insight_ids.contains(&e.b)
            || skill_ids.contains(&e.a)
        {
            continue;
        }
        skill_ids.insert(e.a.clone());
        let rows = value["skills"].as_array_mut().unwrap();
        if rows.len() >= limit {
            omitted_skills += 1;
            continue;
        }
        if let Some(node) = graph.nodes.iter().find(|n| n.id == e.a) {
            rows.push(
                json!({"rank":rows.len()+1,"node":node,"method":"reviewed insight link","via":e.b}),
            );
        }
    }
    value["linked_context"] = json!({"omitted_insights":omitted,"omitted_skills":omitted_skills,"meaning":"Direct ranks stay first. Linked context is appended, not a query match or confidence score. Inspect graph/related for omitted links."});
    let mut shown = bookmark_ids.clone();
    for key in ["insights", "skills", "sessions"] {
        shown.extend(
            value[key]
                .as_array()
                .into_iter()
                .flatten()
                .filter_map(|r| r["node"]["id"].as_str().map(str::to_owned)),
        );
    }
    value["connections"] = json!(
        graph
            .edges
            .iter()
            .filter(|e| [
                "derived_from",
                "references",
                "inspected_version",
                "captured_from",
                "part_of"
            ]
            .contains(&e.kind.as_str())
                && (shown.contains(&e.a) || shown.contains(&e.b)))
            .collect::<Vec<_>>()
    );
}
