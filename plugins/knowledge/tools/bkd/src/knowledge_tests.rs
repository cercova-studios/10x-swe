use super::*;
use crate::{graph, index, model::Record};
const ENTRY: &str = "aaaaaaaaaaaaaaaaaaaaaaaa";
#[test]
fn workflow_v2_is_searchable_inert_metadata_with_graph_navigation() {
    let mut packet = records()[1].clone();
    packet["schema"] = json!("knowledge-snapshot/v2");
    let id = "workflow:global/test/workflows/learning";
    let mut workflow = packet["nodes"][0].clone();
    workflow["id"] = json!(id);
    workflow["kind"] = json!("workflow");
    workflow["details"]["runner"] = json!("/unavailable/never-execute/runner.yaml");
    packet["nodes"].as_array_mut().unwrap().push(workflow);
    packet["versions"][id] = json!("a".repeat(64));
    packet["edges"] = json!([{"a":"skill:global/test","b":id,"kind":"skill_associated_workflow","status":"declared","evidence":{}}]);
    packet["hits"][0]["id"] = json!(id);
    let cfg = config(&[packet.clone()]).unwrap();
    let tmp = tempfile::tempdir().unwrap();
    let home = tmp.path();
    state::prepare(home).unwrap();
    let snapshot = Snapshot::load(home, &cfg).unwrap();
    let g = snapshot
        .enrich(home, books(home, "https://example.com"))
        .unwrap();
    assert_eq!(g.path("skill:global/test", id).unwrap().len(), 1);
    assert_eq!(
        search(&snapshot, &cfg, "locked evidence", 3).unwrap()["skills"][0]["node"]["kind"],
        "workflow"
    );
    packet["schema"] = json!("knowledge-snapshot/v1");
    assert!(config(&[packet]).is_err());
}
fn records() -> Vec<Value> {
    let entry = format!("entry:{ENTRY}");
    let insight = format!("insight:{ENTRY}:1");
    let version = "a".repeat(64);
    let details = json!({"version":version,"coverage":{"line_ranges":[[1,1]],"limitations":["Text only"]},"insights":[{"claim":"Locked snapshots preserve evidence.","evidence":[{"line_start":1,"line_end":1,"quote":"Locked snapshots preserve evidence."}]}],"claim":"Locked snapshots preserve evidence.","status":"source-claim","application":"Pin evidence","evidence":[{"line_start":1,"line_end":1,"quote":"Locked snapshots preserve evidence."}],"note":"/nonexistent/never-open/note.md"});
    vec![
        json!({"schema":"knowledge-snapshot/v1","corpus":"insights","query":"locked evidence","nodes":[{"id":entry,"label":"Locked evidence","kind":"source_entry","url":"https://openai.com/index/research/","bookmark_kind":null,"details":details},{"id":insight,"label":"Locked snapshots preserve evidence.","kind":"insight","url":"https://openai.com/index/research/","bookmark_kind":null,"details":details}],"edges":[{"a":insight,"b":entry,"kind":"derived_from","status":"recorded","evidence":{"citations":details["evidence"]}}],"versions":{entry.clone():version,insight.clone():version},"hits":[{"id":insight,"rank":1,"method":"hybrid","matched_by":["semantic","keyword"]}]}),
        json!({"schema":"knowledge-snapshot/v1","corpus":"skills","query":"locked evidence","nodes":[{"id":"skill:global/test","label":"test","kind":"skill","url":null,"bookmark_kind":null,"details":{"description":"locked evidence","sha256":version,"path":"/nonexistent/never-open/SKILL.md"}}],"edges":[],"versions":{"skill:global/test":version},"hits":[{"id":"skill:global/test","rank":1,"method":"lexical","matched_by":["lexical"]}]}),
    ]
}
fn config(records: &[Value]) -> Result<Config> {
    Config::read(
        records
            .iter()
            .map(|v| v.to_string() + "\n")
            .collect::<String>()
            .as_bytes(),
    )
}
#[test]
fn session_records_validate_unicode_citations_and_recorded_membership() {
    let sid = "session:codex:fixture";
    let tid = "turn:codex:fixture:3";
    let version = "a".repeat(64);
    let quote = "Public 🦀 evidence";
    let citation = json!({"version":version,"coverage":{"limitations":["Selected excerpt"]},"agent":"codex","session_id":"fixture","source_path":"/unavailable/session.jsonl","jsonl_line":3,"json_pointer":"$.payload.content","role":"assistant","timestamp":null,"record_sha256":version,"original_text_sha256":version,"indexed_text_sha256":"b".repeat(64),"excerpt_sha256":hash(quote.as_bytes()),"char_start":0,"char_end":quote.chars().count(),"redacted":false,"quote":quote,"session_revision":version});
    let packet = json!({"schema":"knowledge-snapshot/v1","corpus":"sessions","query":"evidence","nodes":[{"id":sid,"label":"Session fixture","kind":"session","url":null,"bookmark_kind":null,"details":{"version":version,"coverage":{"limitations":["Selected excerpts"]}}},{"id":tid,"label":"Assistant turn","kind":"session_turn","url":null,"bookmark_kind":null,"details":citation}],"edges":[{"a":tid,"b":sid,"kind":"part_of","status":"recorded","evidence":citation}],"versions":{sid:version,tid:version},"hits":[{"id":sid,"rank":1,"method":"naive","matched_by":["naive"]}]});
    assert!(config(std::slice::from_ref(&packet)).is_ok());
    for (field, value) in [
        ("quote", json!("tampered")),
        ("char_end", json!(quote.len())),
        ("jsonl_line", json!(true)),
        ("role", json!("analysis")),
        ("record_sha256", json!("c".repeat(64))),
    ] {
        let mut invalid = packet.clone();
        invalid["nodes"][1]["details"][field] = value;
        assert!(config(&[invalid]).is_err(), "{field}");
    }
    let mut invalid = packet;
    invalid["edges"] = json!([]);
    assert!(config(&[invalid]).is_err());
}
fn fixture() -> (tempfile::TempDir, Config, std::path::PathBuf) {
    let tmp = tempfile::tempdir().unwrap();
    let home = tmp.path().join("state");
    state::prepare(&home).unwrap();
    let cfg = config(&records()).unwrap();
    (tmp, cfg, home)
}
fn books(home: &Path, url: &str) -> Graph {
    let db = state::db(home).unwrap();
    let r = Record::new("raindrop", "test", "1", url).unwrap();
    graph::derive(&db, &index::merge(vec![r], &[], &[], None), false).unwrap()
}
#[test]
fn exact_url_join_keeps_citations_and_never_opens_producer_paths() {
    let (_tmp, cfg, home) = fixture();
    let s = Snapshot::load(&home, &cfg).unwrap();
    let base = books(&home, "https://openai.com/index/research/");
    let id = base.nodes[0].id.clone();
    let g = s.enrich(&home, base).unwrap();
    assert_eq!(g.path(&id, &format!("insight:{ENTRY}:1")).unwrap().len(), 2);
    let d = s.detail(&g, &id).unwrap();
    assert_eq!(
        d["node"]["details"]["inspected_sources"][0]["details"]["insights"][0]["evidence"][0]["line_start"],
        1
    );
    let other = s
        .enrich(
            &home,
            books(&home, "https://openai.com/index/research/?different=1"),
        )
        .unwrap();
    assert!(!other.edges.iter().any(|e| e.kind == "inspected_version"));
    let result = search(&s, &cfg, "locked evidence", 3).unwrap();
    assert_eq!(result["insights"][0]["method"], "hybrid");
    assert_eq!(result["skills"][0]["rank"], 1);
    let local = search(&s, &cfg, "preserve snapshots", 3).unwrap();
    assert_eq!(local["insights"][0]["method"], "snapshot lexical");
    assert_eq!(local["knowledge"]["query_scope"][0]["used_ranks"], false);
}
#[test]
fn reviewed_links_pin_supplied_revisions_and_serialize_writers() {
    let (_tmp, cfg, home) = fixture();
    let s = Snapshot::load(&home, &cfg).unwrap();
    let iid = format!("insight:{ENTRY}:1");
    assert!(
        s.review_link(&home, "skill:global/test", &iid, "", false, false)
            .is_err()
    );
    s.review_link(
        &home,
        "skill:global/test",
        &iid,
        "Reviewed applicability",
        false,
        true,
    )
    .unwrap();
    assert!(
        s.review_link(
            &home,
            "skill:global/test",
            &iid,
            "Stale writer",
            false,
            true
        )
        .is_err()
    );
    let current = Snapshot::load(&home, &cfg).unwrap();
    assert!(current.edges.iter().any(|e| e.kind == "references"));
    let mut packets = records();
    let new = "b".repeat(64);
    packets[0]["versions"][&iid] = json!(new);
    packets[0]["nodes"][1]["details"]["version"] = json!(new);
    let cfg = config(&packets).unwrap();
    let changed = Snapshot::load(&home, &cfg).unwrap();
    assert!(!changed.edges.iter().any(|e| e.kind == "references"));
    assert_eq!(changed.status["stale_links"].as_array().unwrap().len(), 1);
    changed
        .review_link(&home, "skill:global/test", &iid, "", true, false)
        .unwrap();
    assert!(links(&home).unwrap().links.is_empty());
}
#[test]
fn input_rejects_missing_revisions_unresolved_edges_bad_ranks_and_truncation() {
    assert!(Config::read("".as_bytes()).is_err());
    assert!(Config::read(&[0xff][..]).is_err());
    assert!(Config::read("{\"schema\":".as_bytes()).is_err());
    for mutate in 0..7 {
        let mut rows = records();
        match mutate {
            0 => rows[0]["schema"] = json!("old"),
            1 => rows[0]["versions"] = json!({}),
            2 => rows[0]["edges"][0]["b"] = json!("entry:missing"),
            3 => rows[0]["hits"][0]["rank"] = json!(2),
            4 => rows[0]["nodes"][1]["details"]["evidence"] = json!([]),
            5 => rows.push(rows[0].clone()),
            _ => rows[0]["command"] = json!("not allowed"),
        }
        assert!(config(&rows).is_err(), "case {mutate}");
    }
    assert!(Config::read(std::io::repeat(b'x').take(32 * 1024 * 1024 + 1)).is_err());
}
#[test]
fn immediate_inspection_skips_unrelated_vectors() {
    let (_tmp, cfg, home) = fixture();
    let mut db = state::db(&home).unwrap();
    let r = Record::new(
        "raindrop",
        "test",
        "1",
        "https://openai.com/index/research/",
    )
    .unwrap();
    index::publish(
        &mut db,
        &[("raindrop".into(), "test".into(), vec![r])],
        0,
        false,
        None,
    )
    .unwrap();
    let s = Snapshot::load(&home, &cfg).unwrap();
    db.execute(
        "INSERT INTO vectors VALUES(?1,?2,?3)",
        rusqlite::params![hash("fixture"), crate::embedding::SPEC, vec![0u8]],
    )
    .unwrap();
    assert!(
        s.inspect(
            &mut db,
            &home,
            &search::Filter::default(),
            &format!("insight:{ENTRY}:1")
        )
        .is_ok()
    );
}

#[test]
fn recorded_context_surfaces_linked_skills_without_comparing_scores() {
    let (_tmp, cfg, home) = fixture();
    let s = Snapshot::load(&home, &cfg).unwrap();
    let iid = format!("insight:{ENTRY}:1");
    s.review_link(
        &home,
        "skill:global/test",
        &iid,
        "Reviewed relation",
        false,
        true,
    )
    .unwrap();
    let s = Snapshot::load(&home, &cfg).unwrap();
    let base = books(&home, "https://openai.com/index/research/");
    let id = base.nodes[0].id.clone();
    let g = s.enrich(&home, base).unwrap();
    let mut results = json!({"insights":[],"skills":[]});
    contextualize(&mut results, &g, &BTreeSet::from([id.clone()]), 2);
    assert_eq!(results["insights"][0]["node"]["id"], iid);
    assert_eq!(results["skills"][0]["node"]["id"], "skill:global/test");
    assert_eq!(results["skills"][0]["method"], "reviewed insight link");
    assert!(results["skills"][0].get("score").is_none());
    let mut unrelated = g.clone();
    unrelated.edges.push(Edge {
        a: "insight:unrelated:1".into(),
        b: "entry:unrelated".into(),
        kind: "derived_from".into(),
        status: "recorded".into(),
        evidence: json!({}),
    });
    let mut focused = json!({"insights":[],"skills":[]});
    contextualize(&mut focused, &unrelated, &BTreeSet::from([id.clone()]), 2);
    assert_eq!(focused["connections"].as_array().unwrap().len(), 3);
    let mut bounded = json!({"insights":[{"node":{"id":"direct"},"rank":1}],"skills":[]});
    contextualize(&mut bounded, &g, &BTreeSet::from([id]), 1);
    assert_eq!(bounded["insights"][0]["node"]["id"], "direct");
    assert_eq!(bounded["linked_context"]["omitted_insights"], 1);
    let mut duplicate = g.clone();
    duplicate.edges.push(
        g.edges
            .iter()
            .find(|e| e.kind == "references")
            .unwrap()
            .clone(),
    );
    let mut full = json!({"insights":[{"node":{"id":iid},"rank":1}],"skills":[{"node":{"id":"direct-skill"},"rank":1}]});
    contextualize(&mut full, &duplicate, &BTreeSet::new(), 1);
    assert_eq!(full["linked_context"]["omitted_skills"], 1);
}
