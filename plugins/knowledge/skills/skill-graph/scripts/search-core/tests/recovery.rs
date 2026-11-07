use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{fs, process::Command};

#[test]
fn failed_semantic_helper_retains_diagnostics_and_offers_an_exact_lexical_retry() {
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().canonicalize().unwrap();
    let skills = root.join("skills");
    fs::create_dir_all(skills.join("evidence")).unwrap();
    fs::create_dir_all(skills.join("other")).unwrap();
    let source = skills.join("evidence/SKILL.md");
    let text = b"---\nname: evidence\ndescription: cite evidence\n---\nRead evidence.\n";
    fs::write(&source, text).unwrap();
    let hash = format!("{:x}", Sha256::digest(text));
    let other = skills.join("other/SKILL.md");
    fs::write(&other, text).unwrap();
    let graph = root.join("graph fixture.json");
    fs::write(&graph, json!({"schema":1,"errors":[],"roots":[{"path":skills}],
        "nodes":[{"id":"global/evidence","name":"evidence","description":"cite evidence","scope":"global",
                  "path":source,"discovery_path":source,"sha256":hash,"declared_used_by":[],"used_by":[]},
                 {"id":"global/other","name":"other","description":"unrelated","scope":"global",
                  "path":other,"discovery_path":other,"sha256":hash,"declared_used_by":[],"used_by":[]}],
        "aliases":[],"edges":[],"concepts":{"status":"fresh","records":[{"id":"global/evidence","entrypoint_sha256":hash},{"id":"global/other","entrypoint_sha256":hash}]}}).to_string()).unwrap();
    let helper = root.join("failed helper.sh");
    fs::write(
        &helper,
        "printf 'Traceback: injected Metal failure\\n' >&2\nexit 1\n",
    )
    .unwrap();
    let state = root.join("selected state");
    let query = "cite evidence 'quoted; task'";
    let binary = env!("CARGO_BIN_EXE_skill-search");
    let output = Command::new(binary)
        .args([
            "--graph",
            graph.to_str().unwrap(),
            "--state",
            state.to_str().unwrap(),
            "path",
            query,
            "--limit",
            "1",
            "--semantic",
            "--python",
            "/bin/sh",
            "--helper",
            helper.to_str().unwrap(),
        ])
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(1));
    assert!(output.stdout.is_empty());
    let error: Value = serde_json::from_slice(&output.stderr).unwrap();
    assert_eq!(error["status"], "failed");
    assert_eq!(error["code"], "mapping_helper_failed");
    assert!(!error.to_string().contains("Traceback"));
    let diagnostics = std::path::PathBuf::from(error["diagnostics"].as_str().unwrap());
    assert!(
        fs::read_to_string(diagnostics.join("stderr"))
            .unwrap()
            .contains("injected Metal failure")
    );
    assert!(diagnostics.join("failure.txt").is_file());
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        assert_eq!(
            fs::metadata(&diagnostics).unwrap().permissions().mode() & 0o077,
            0
        );
    }
    let argv: Vec<_> = error["recovery"]["argv"]
        .as_array()
        .unwrap()
        .iter()
        .map(|a| a.as_str().unwrap())
        .collect();
    assert_eq!(
        argv,
        [
            binary,
            "--state",
            state.to_str().unwrap(),
            "--graph",
            graph.to_str().unwrap(),
            "path",
            query,
            "--limit",
            "1"
        ]
    );
    let retry = Command::new(argv[0]).args(&argv[1..]).output().unwrap();
    assert!(
        retry.status.success(),
        "{}",
        String::from_utf8_lossy(&retry.stderr)
    );
    let result: Value = serde_json::from_slice(&retry.stdout).unwrap();
    assert_eq!(result["method"], "lexical_seed_plus_typed_graph");
    assert_eq!(
        result["candidate_paths"][0]["entrypoint"],
        "global/evidence"
    );
    fs::remove_dir_all(diagnostics).unwrap();

    let exported = Command::new(binary)
        .args([
            "--graph",
            graph.to_str().unwrap(),
            "--state",
            state.to_str().unwrap(),
            "export",
        ])
        .output()
        .unwrap();
    assert!(
        exported.status.success(),
        "{}",
        String::from_utf8_lossy(&exported.stderr)
    );
    assert_eq!(exported.stdout.iter().filter(|b| **b == b'\n').count(), 1);
    let packet: Value = serde_json::from_slice(&exported.stdout).unwrap();
    assert_eq!(packet["schema"], "knowledge-snapshot/v2");

    // Invalid helper output must never become a successful or partial pipe record.
    fs::write(&helper, "printf 'not JSON'\n").unwrap();
    let invalid = Command::new(binary)
        .args([
            "--graph",
            graph.to_str().unwrap(),
            "path",
            query,
            "--semantic",
            "--python",
            "/bin/sh",
            "--helper",
            helper.to_str().unwrap(),
        ])
        .output()
        .unwrap();
    assert_eq!(invalid.status.code(), Some(1));
    assert!(invalid.stdout.is_empty());
    let error: Value = serde_json::from_slice(&invalid.stderr).unwrap();
    assert_eq!(error["code"], "mapping_helper_failed");
    let diagnostics = std::path::PathBuf::from(error["diagnostics"].as_str().unwrap());
    assert_eq!(fs::read(diagnostics.join("stdout")).unwrap(), b"not JSON");
    fs::remove_dir_all(diagnostics).unwrap();

    fs::write(&helper, "printf '[{\"id\":\"global/evidence\",\"score\":1},{\"id\":\"global/other\",\"score\":0}]'\nhead -c 131073 /dev/zero >&2\n").unwrap();
    let oversized = Command::new(binary)
        .args([
            "--graph",
            graph.to_str().unwrap(),
            "path",
            query,
            "--semantic",
            "--python",
            "/bin/sh",
            "--helper",
            helper.to_str().unwrap(),
        ])
        .output()
        .unwrap();
    assert_eq!(oversized.status.code(), Some(1));
    assert!(oversized.stdout.is_empty());
    let error: Value = serde_json::from_slice(&oversized.stderr).unwrap();
    assert_eq!(error["code"], "mapping_helper_failed");
    fs::remove_dir_all(error["diagnostics"].as_str().unwrap()).unwrap();
}
