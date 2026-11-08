use crate::{
    model::SearchResult,
    store::Store,
    text::{redact, revision_json, sha},
    turns,
};
use anyhow::{Context, Result, ensure};
use serde_json::{Value, json};
pub fn export(store: &Store, result: &SearchResult, role: Option<&str>) -> Result<Value> {
    let (mut nodes, mut edges, mut hits) = (Vec::new(), Vec::new(), Vec::new());
    let mut versions = serde_json::Map::new();
    for (n, hit) in result.hits.iter().enumerate() {
        let rec = store
            .get(&hit.agent, &hit.native_id)?
            .context("Selected session changed; retry query")?;
        let citations = turns::excerpts(&rec, &result.query, role);
        ensure!(
            !citations.is_empty(),
            "Selected session has no exact matching turn provenance; refresh a supported adapter or use another query"
        );
        let sid = format!("session:{}", rec.id());
        let revision = sha(revision_json(
            &json!({"turns":rec.turns,"limitations":rec.limitations}),
        ));
        let mut limits = vec![json!(
            "Selected public-text excerpts, not a reviewed full transcript."
        )];
        limits.extend(rec.limitations.iter().map(|s| json!(s)));
        let description = citations
            .iter()
            .filter_map(|c| c["quote"].as_str())
            .collect::<Vec<_>>()
            .join("\n");
        let details = json!({"agent":rec.agent,"session_id":rec.native_id,"cwd":rec.cwd,"updated_at":rec.updated_at,"source_path":rec.source_path,"version":revision,"coverage":{"limitations":limits},"open_with":["session-search","show",rec.agent,rec.native_id,"--json"],"summary":redact(&rec.summary),"description":description,"evidence":citations,"authority":"Discovery evidence, not verified findings or permission."});
        nodes.push(json!({"id":sid,"label":rec.title,"kind":"session","url":null,"bookmark_kind":null,"details":details}));
        versions.insert(sid.clone(), json!(revision));
        for citation in citations {
            let tid = format!("turn:{}:{}", rec.id(), citation["jsonl_line"]);
            let mut details = citation.clone();
            details["version"] = citation["record_sha256"].clone();
            details["evidence"] = json!([citation]);
            details["coverage"] = json!({"limitations":[citation["coverage"]]});
            details["description"] = citation["quote"].clone();
            details["session_revision"] = json!(revision);
            nodes.push(json!({"id":tid,"label":format!("{} · line {}",citation["role"].as_str().unwrap_or(""),citation["jsonl_line"]),"kind":"session_turn","url":null,"bookmark_kind":null,"details":details}));
            versions.insert(tid.clone(), citation["record_sha256"].clone());
            edges.push(
                json!({"a":tid,"b":sid,"kind":"part_of","status":"recorded","evidence":citation}),
            );
        }
        hits.push(json!({"id":sid,"rank":n+1,"method":hit.strategy,"matched_by":[hit.strategy]}));
    }
    let packet = json!({"schema":"knowledge-snapshot/v1","corpus":"sessions","query":result.query,"nodes":nodes,"edges":edges,"versions":versions,"hits":hits});
    ensure!(
        revision_json(&packet).len() <= 16 * 1024 * 1024,
        "Export exceeds 16 MiB"
    );
    Ok(packet)
}
