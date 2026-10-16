use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::process::Command;
fn binary() -> Command {
    Command::new(env!("CARGO_BIN_EXE_bkd"))
}
#[test]
fn portable_stdin_is_data_and_invalid_stream_preserves_snapshot() {
    use std::{io::Write, process::Stdio};
    let tmp = tempfile::tempdir().unwrap();
    let home = tmp.path().join("state");
    let run = |bytes: &[u8]| {
        let mut child = binary()
            .arg("--home")
            .arg(&home)
            .args(["index", "-", "--lexical-only", "--json"])
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .unwrap();
        child.stdin.take().unwrap().write_all(bytes).unwrap();
        child.wait_with_output().unwrap()
    };
    let record=b"{\"provider\":\"manual\",\"account\":\"fixture\",\"external_id\":\"1\",\"url\":\"https://example.org/one\"}\n";
    assert!(run(record).status.success());
    let before = binary()
        .arg("--home")
        .arg(&home)
        .arg("export")
        .output()
        .unwrap();
    assert_eq!(
        serde_json::from_slice::<Value>(&before.stdout).unwrap()["url"],
        "https://example.org/one"
    );
    let malformed = [record.as_slice(), b"not a record\n"].concat();
    assert!(!run(&malformed).status.success());
    let after = binary()
        .arg("--home")
        .arg(&home)
        .arg("export")
        .output()
        .unwrap();
    assert_eq!(before.stdout, after.stdout);
    let imported = run(&before.stdout);
    assert!(imported.status.success());
    let interactive = binary().args(["--json"]).output().unwrap();
    assert!(!interactive.status.success());
    assert!(
        String::from_utf8(interactive.stdout)
            .unwrap()
            .contains("TUI requires a terminal")
    );
    let removed = binary().arg("tui").output().unwrap();
    assert!(!removed.status.success());
}

#[test]
fn search_defaults_to_url_and_lists_are_explicit() {
    let tmp = tempfile::tempdir().unwrap();
    let home = tmp.path().join("state");
    let fixture = tmp.path().join("bookmarks.jsonl");
    std::fs::write(&fixture, concat!(
        "{\"provider\":\"instapaper\",\"account\":\"fixture\",\"external_id\":\"1\",\"url\":\"https://huyenchip.com\",\"title\":\"Chip Huyen blog\",\"kind\":\"other\",\"kind_source\":\"unknown\"}\n",
        "{\"provider\":\"instapaper\",\"account\":\"fixture\",\"external_id\":\"2\",\"url\":\"https://example.com/blog/notes\",\"title\":\"Blog notes\"}\n"
    )).unwrap();
    assert!(
        binary()
            .arg("--home")
            .arg(&home)
            .arg("index")
            .arg(&fixture)
            .arg("--lexical-only")
            .output()
            .unwrap()
            .status
            .success()
    );
    let run = |extra: &[&str]| {
        binary()
            .arg("--home")
            .arg(&home)
            .args(["search", "Chip Huyen blog", "--lexical-only"])
            .args(extra)
            .output()
            .unwrap()
    };
    for extra in [vec![], vec!["--limit", "2"]] {
        let out = run(&extra);
        assert!(
            out.status.success(),
            "{}",
            String::from_utf8_lossy(&out.stderr)
        );
        assert_eq!(
            String::from_utf8(out.stdout).unwrap(),
            "https://huyenchip.com\n"
        );
    }
    let listed = run(&["--list", "--kind", "blog"]);
    assert!(listed.status.success());
    let listed = String::from_utf8(listed.stdout).unwrap();
    assert_eq!(listed.lines().count(), 2);
    assert!(listed.starts_with("1\tblog\t"));
    let rich = run(&["--rich"]);
    assert!(rich.status.success());
    assert_eq!(String::from_utf8(rich.stdout).unwrap().lines().count(), 2);
    let out = run(&["--json"]);
    assert!(out.status.success());
    let value: Value = serde_json::from_slice(&out.stdout).unwrap();
    assert_eq!(value["data"]["results"].as_array().unwrap().len(), 2);
    let missing = run(&["--kind", "paper"]);
    assert!(!missing.status.success());
    assert!(missing.stdout.is_empty());
    assert!(
        String::from_utf8(missing.stderr)
            .unwrap()
            .contains("No matching bookmarks")
    );
    let graph = binary()
        .arg("--home")
        .arg(&home)
        .args(["graph", "--json"])
        .output()
        .unwrap();
    assert!(graph.status.success());
    let g: Value = serde_json::from_slice(&graph.stdout).unwrap();
    assert!(
        g["data"]["edges"]
            .as_array()
            .unwrap()
            .iter()
            .all(|e| e["kind"] != "similar")
    );
    assert!(
        binary()
            .args(["graph", "--help"])
            .output()
            .unwrap()
            .status
            .success()
    );
    assert!(
        !binary()
            .args(["graph", "--no-similarity"])
            .output()
            .unwrap()
            .status
            .success()
    );
}

#[test]
fn piped_knowledge_search_and_navigation_need_no_companion_tools_or_files() {
    use std::{io::Write, process::Stdio};
    let tmp = tempfile::tempdir().unwrap();
    let home = tmp.path().join("state");
    assert!(
        binary()
            .arg("--home")
            .arg(&home)
            .args(["index", "tests/fixtures/bookmarks.jsonl", "--lexical-only"])
            .output()
            .unwrap()
            .status
            .success()
    );
    let eid = "cccccccccccccccccccccccc";
    let entry = format!("entry:{eid}");
    let insight = format!("insight:{eid}:1");
    let version = "a".repeat(64);
    let source = "https://openai.com/index/interpretability-research/";
    let details = json!({"version":version,"coverage":{"limitations":["Fixture only"]},"insights":[{"evidence":[{"line_start":1,"line_end":1,"quote":"Retained claim."}]}],"claim":"Retained claim.","status":"source-claim","evidence":[{"line_start":1,"line_end":1,"quote":"Retained claim."}],"note":"/not/available/note.md","open_with":["/not/executed"]});
    let mut packet = json!({"schema":"knowledge-snapshot/v1","corpus":"insights","query":"research","nodes":[{"id":entry,"label":"CLI fixture","kind":"source_entry","url":source,"bookmark_kind":null,"details":details},{"id":insight,"label":"Retained claim.","kind":"insight","url":source,"bookmark_kind":null,"details":details}],"edges":[{"a":insight,"b":entry,"kind":"derived_from","status":"recorded","evidence":{"citations":details["evidence"]}}],"versions":{entry.clone():version,insight.clone():version},"hits":[{"id":insight,"rank":1,"method":"hybrid","matched_by":["semantic"]}]});
    let skill = json!({"schema":"knowledge-snapshot/v1","corpus":"skills","query":"research","nodes":[{"id":"skill:fixture/test","label":"fixture","kind":"skill","url":null,"bookmark_kind":null,"details":{"sha256":version,"description":"Evidence","path":"/not/available/SKILL.md"}}],"edges":[],"versions":{"skill:fixture/test":version},"hits":[{"id":"skill:fixture/test","rank":1,"method":"lexical","matched_by":["lexical"]}]});
    let run = |args: &[&str], packet: &Value| {
        let raw = format!("{packet}\n{skill}\n");
        let mut child = binary()
            .arg("--home")
            .arg(&home)
            .args(["--records", "-"])
            .args(args)
            .arg("--json")
            .env("PATH", "/no-companion-executables")
            .env("HOME", tmp.path().join("no-private-libraries"))
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .unwrap();
        child
            .stdin
            .take()
            .unwrap()
            .write_all(raw.as_bytes())
            .unwrap();
        let out = child.wait_with_output().unwrap();
        (
            out.status.success(),
            serde_json::from_slice::<Value>(&out.stdout).unwrap(),
        )
    };
    let bid = format!("{:x}", Sha256::digest(source.as_bytes()));
    let inspected = run(&["inspect", &bid], &packet);
    assert!(inspected.0, "{}", inspected.1);
    assert_eq!(
        inspected.1["data"]["node"]["details"]["inspected_sources"][0]["details"]["insights"][0]["evidence"]
            [0]["line_start"],
        1
    );
    let searched = run(&["search", "research", "--lexical-only"], &packet);
    assert!(searched.0, "{}", searched.1);
    assert_eq!(searched.1["data"]["insights"][0]["method"], "hybrid");
    assert_eq!(searched.1["data"]["skills"][0]["rank"], 1);
    assert!(
        !run(
            &[
                "link-knowledge",
                "skill:fixture/test",
                &insight,
                "--reason",
                "Reviewed fixture"
            ],
            &packet
        )
        .0
    );
    assert!(
        run(
            &[
                "link-knowledge",
                "skill:fixture/test",
                &insight,
                "--reason",
                "Reviewed fixture",
                "--reviewed"
            ],
            &packet
        )
        .0
    );
    assert!(run(&["related", &insight], &packet).0);
    let path = run(&["path", &bid, "skill:fixture/test"], &packet);
    assert!(path.0, "{}", path.1);
    assert_eq!(path.1["data"]["path"].as_array().unwrap().len(), 3);
    let records_file = tmp.path().join("records.jsonl");
    std::fs::write(&records_file, format!("{packet}\n{skill}\n")).unwrap();
    let file = binary()
        .arg("--home")
        .arg(&home)
        .arg("--records")
        .arg(&records_file)
        .args(["graph", "--json"])
        .output()
        .unwrap();
    assert!(file.status.success());
    let new = "b".repeat(64);
    packet["versions"][&insight] = json!(new);
    packet["nodes"][1]["details"]["version"] = json!(new);
    let stale = run(&["graph"], &packet);
    assert!(stale.0);
    assert_eq!(
        stale.1["data"]["knowledge"]["stale_links"]
            .as_array()
            .unwrap()
            .len(),
        1
    );
    assert!(
        run(
            &["link-knowledge", "skill:fixture/test", &insight, "--remove"],
            &packet
        )
        .0
    );
    let before = binary()
        .arg("--home")
        .arg(&home)
        .arg("export")
        .output()
        .unwrap()
        .stdout;
    let invalid = run(
        &["index", "tests/fixtures/bookmarks.jsonl", "--lexical-only"],
        &packet,
    );
    assert!(!invalid.0);
    assert_eq!(
        before,
        binary()
            .arg("--home")
            .arg(&home)
            .arg("export")
            .output()
            .unwrap()
            .stdout
    );
    for flag in ["--knowledge", "--insights-library", "--skill-graph"] {
        assert!(!binary().arg(flag).output().unwrap().status.success());
    }
}

#[test]
fn both_aliases_and_plain_agent_contract() {
    let tmp = tempfile::tempdir().unwrap();
    for binary in [
        env!("CARGO_BIN_EXE_bkd"),
        env!("CARGO_BIN_EXE_bookmarkdrop"),
    ] {
        let result = Command::new(binary).arg("--help").output().unwrap();
        assert!(result.status.success());
        assert!(String::from_utf8(result.stdout).unwrap().contains("import"));
    }
    let indexed = binary()
        .args([
            "--home",
            tmp.path().to_str().unwrap(),
            "index",
            "tests/fixtures/bookmarks.jsonl",
            "--lexical-only",
            "--json",
        ])
        .output()
        .unwrap();
    assert!(indexed.status.success());
    assert_eq!(
        serde_json::from_slice::<serde_json::Value>(&indexed.stdout).unwrap()["data"]["origins"],
        6
    );
    let result = binary()
        .args([
            "--home",
            tmp.path().to_str().unwrap(),
            "search",
            "research",
            "--domain",
            "openai.com",
            "--source",
            "instapaper,raindrop",
            "--kind",
            "blog",
            "--lexical-only",
            "--json",
        ])
        .output()
        .unwrap();
    assert!(result.status.success());
    let value: serde_json::Value = serde_json::from_slice(&result.stdout).unwrap();
    assert_eq!(
        value["data"]["results"][0]["origins"]
            .as_array()
            .unwrap()
            .len(),
        2
    );
    assert!(
        value["data"]["results"]
            .as_array()
            .unwrap()
            .iter()
            .all(|r| !r["url"].as_str().unwrap().contains("evil"))
    );
    let export = binary()
        .args(["--home", tmp.path().to_str().unwrap(), "export"])
        .output()
        .unwrap();
    assert!(export.status.success());
    assert_eq!(String::from_utf8(export.stdout).unwrap().lines().count(), 6);
    let artifact = tmp.path().join("relationships.json");
    std::fs::write(&artifact, r#"{"schema":1,"relationships":[]}"#).unwrap();
    let preview = binary()
        .args([
            "--home",
            tmp.path().to_str().unwrap(),
            "import",
            artifact.to_str().unwrap(),
            "--relationships",
            "--dry-run",
            "--json",
        ])
        .env_remove("BKD_DATABASE_URL")
        .output()
        .unwrap();
    assert!(preview.status.success());
    assert_eq!(
        serde_json::from_slice::<serde_json::Value>(&preview.stdout).unwrap()["data"]["applied"],
        false
    );
    let graph = binary()
        .args(["--home", tmp.path().to_str().unwrap(), "graph"])
        .output()
        .unwrap();
    assert!(!graph.status.success());
    assert!(
        String::from_utf8(graph.stderr)
            .unwrap()
            .contains("terminal")
    );
    let unattended = binary()
        .args([
            "--home",
            tmp.path().to_str().unwrap(),
            "save",
            "https://a.com",
            "--json",
        ])
        .output()
        .unwrap();
    assert!(!unattended.status.success());
    assert_eq!(
        serde_json::from_slice::<serde_json::Value>(&unattended.stdout).unwrap()["ok"],
        false
    );
}

#[test]
fn unified_sync_validates_modes_and_preserves_cache_on_embedding_failure() {
    let tmp = tempfile::tempdir().unwrap();
    let home = tmp.path().to_str().unwrap();
    let offline = binary()
        .args(["--home", home, "sync", "--offline", "--json"])
        .env("BKD_INSTAPAPER_TOKEN", "invalid-fixture-token")
        .env("BKD_RAINDROP_TOKEN", "invalid-fixture-token")
        .env("BKD_DATABASE_URL", "invalid-fixture-url")
        .output()
        .unwrap();
    assert!(offline.status.success());
    let value: serde_json::Value = serde_json::from_slice(&offline.stdout).unwrap();
    assert_eq!(value["data"]["refreshed"], serde_json::json!([]));
    assert_eq!(value["data"]["indexed"], true);
    for extra in ["--source=instapaper", "--lexical-only"] {
        let result = binary()
            .args(["sync", "--offline", extra])
            .output()
            .unwrap();
        assert!(!result.status.success());
        assert!(
            String::from_utf8(result.stderr)
                .unwrap()
                .contains("cannot be used")
        );
    }
    let indexed = binary()
        .args([
            "--home",
            home,
            "index",
            "tests/fixtures/bookmarks.jsonl",
            "--lexical-only",
        ])
        .output()
        .unwrap();
    assert!(indexed.status.success());
    let failed = binary()
        .args(["--home", home, "sync", "--offline", "--json"])
        .env("BKD_MODEL_PATH", tmp.path().join("missing.gguf"))
        .output()
        .unwrap();
    assert!(!failed.status.success());
    assert!(
        String::from_utf8(failed.stdout)
            .unwrap()
            .contains("Local BGE model missing")
    );
    let exported = binary().args(["--home", home, "export"]).output().unwrap();
    assert!(exported.status.success());
    assert_eq!(
        String::from_utf8(exported.stdout).unwrap().lines().count(),
        6
    );
    let old = binary().args(["reindex"]).output().unwrap();
    assert!(!old.status.success());
}
