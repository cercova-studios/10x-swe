//! Portable snapshot output; consumers never need the private catalog/graph format.
use anyhow::{Context, Result, ensure};
use serde_json::{Value, json};
pub fn export(graph: &Value, query: Option<&str>, hits: &[Value]) -> Result<Value> {
    let mut nodes = Vec::new();
    let mut versions = serde_json::Map::new();
    let mut ids = std::collections::BTreeMap::new();
    for n in graph["nodes"].as_array().context("Missing skill nodes")? {
        let scoped = n["id"].as_str().context("Missing skill ID")?;
        let kind = n["kind"].as_str().unwrap_or("skill");
        ensure!(
            matches!(kind, "skill" | "workflow"),
            "Unknown discovery kind"
        );
        let id = format!("{kind}:{scoped}");
        ids.insert(scoped.to_owned(), id.clone());
        let revision = if kind == "workflow" {
            json!(crate::bundle::hash(&serde_json::to_vec(
                &json!({"document":n["sha256"],"resources":n["resources"]})
            )?))
        } else {
            n["sha256"].clone()
        };
        versions.insert(id.clone(), revision.clone());
        nodes.push(json!({"id":id,"label":n["name"],"kind":kind,"url":null,"bookmark_kind":null,"details":{"scoped_id":scoped,"description":n["description"],"sha256":revision,"document_sha256":n["sha256"],"runner":n["runner"],"resources":n["resources"],"path":n["path"],"read_only":n["read_only"],"trust":n["trust"],"original_id":n["original_id"],"unresolved_references":n["unresolved_references"],"open_with":["skill-search","load",scoped],"authority":"Discovery metadata only; execution and approval require explicit operator action."}}));
    }
    let mut edges = Vec::new();
    for e in graph["edges"].as_array().context("Missing skill edges")? {
        let a = ids
            .get(e["source"].as_str().context("Missing edge source")?)
            .context("Unresolved edge source")?
            .clone();
        let b = ids
            .get(e["target"].as_str().context("Missing edge target")?)
            .context("Unresolved edge target")?
            .clone();
        ensure!(
            versions.contains_key(&a) && versions.contains_key(&b),
            "Unresolved skill edge"
        );
        edges.push(json!({"a":a,"b":b,"kind":format!("skill_{}",e["relation"].as_str().context("Missing relation")?),"status":e["status"].as_str().unwrap_or("declared"),"evidence":e}));
    }
    let hits=hits.iter().enumerate().map(|(rank,h)|json!({"id":ids.get(h["id"].as_str().unwrap()),"rank":rank+1,"method":"lexical","matched_by":["lexical"]})).collect::<Vec<_>>();
    let out = json!({"schema":"knowledge-snapshot/v2","corpus":"skills","query":query,"nodes":nodes,"edges":edges,"versions":versions,"hits":hits});
    ensure!(
        serde_json::to_vec(&out)?.len() <= 16 * 1024 * 1024
            && out["nodes"].as_array().unwrap().len() <= 10000
            && out["edges"].as_array().unwrap().len() <= 100000,
        "Snapshot exceeds export limits"
    );
    Ok(out)
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn workflow_exports_keep_types_closed_edges_and_resource_revision() {
        let mut graph = json!({"nodes":[{"id":"global/owner","name":"Owner","sha256":"a".repeat(64)}, {"id":"global/owner/workflows/learn","name":"Learn","kind":"workflow","sha256":"b".repeat(64),"resources":{"runner.yaml":"c".repeat(64)}}],"edges":[{"source":"global/owner","target":"global/owner/workflows/learn","relation":"associated_workflow"}]});
        let first = export(
            &graph,
            Some("learn"),
            &[json!({"id":"global/owner/workflows/learn"})],
        )
        .unwrap();
        let id = "workflow:global/owner/workflows/learn";
        assert_eq!(first["schema"], "knowledge-snapshot/v2");
        assert_eq!(first["nodes"][1]["kind"], "workflow");
        assert_eq!(first["edges"][0]["b"], id);
        assert_eq!(first["edges"][0]["status"], "declared");
        assert_eq!(first["hits"][0]["id"], id);
        graph["nodes"][1]["resources"]["runner.yaml"] = json!("d".repeat(64));
        assert_ne!(
            first["versions"][id],
            export(&graph, None, &[]).unwrap()["versions"][id]
        );
    }
    #[test]
    fn output_preserves_ids_revisions_relationship_status_and_separate_ranks() {
        let graph = json!({"nodes":[{"id":"global/test","name":"Test","description":"Evidence","sha256":"a".repeat(64),"path":"/not/consumer/read/SKILL.md"}],"edges":[{"source":"global/test","target":"global/test","relation":"related","status":"inferred"}]});
        let p = export(&graph, Some("evidence"), &[json!({"id":"global/test"})]).unwrap();
        assert_eq!(p["nodes"][0]["id"], "skill:global/test");
        assert_eq!(p["hits"][0]["rank"], 1);
        assert_eq!(p["versions"]["skill:global/test"], "a".repeat(64));
        assert_eq!(p["edges"][0]["status"], "inferred");
        let mut broken = graph;
        broken["edges"][0]["target"] = json!("global/missing");
        assert!(export(&broken, None, &[]).is_err());
    }
}
