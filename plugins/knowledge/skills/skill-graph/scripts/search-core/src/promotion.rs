//! Explicit new-skill promotion. Existing skills and graph relationships are never overwritten.
use crate::bundle;
use anyhow::{Context, Result, ensure};
use serde_json::{Value, json};
use std::{fs, io::Write, path::Path, process::Command};

pub fn install(
    prepared: &Path,
    graph: &Path,
    root_id: &str,
    python: &Path,
    helper: &Path,
) -> Result<Value> {
    let receipt: Value = serde_json::from_slice(&bundle::read_bounded(
        &prepared.join("receipt.json"),
        8 * 1024 * 1024,
    )?)?;
    let accepted = bundle::load(&prepared.join("bundle"), &receipt, "SKILL.md")?;
    let text = accepted["content"]
        .as_str()
        .context("missing accepted entrypoint")?;
    let yaml = text
        .lines()
        .skip(1)
        .take_while(|line| line.trim() != "---")
        .collect::<Vec<_>>()
        .join("\n");
    let meta: Value = serde_yaml_ng::from_str(&yaml)?;
    let name = meta["name"].as_str().context("missing name")?;
    ensure!(
        ![
            "uses",
            "used-by",
            "related",
            "references",
            "related-inferred",
            "skill-id",
            "topic-clusters"
        ]
        .iter()
        .any(|key| meta.get(key).is_some()),
        "portable relationship metadata requires staged annotation and renewed scan; use graph maintenance workflow"
    );
    ensure!(
        !name.is_empty()
            && name.len() <= 64
            && !name.starts_with('-')
            && !name.ends_with('-')
            && !name.contains("--")
            && name
                .bytes()
                .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == b'-'),
        "invalid install folder name"
    );
    if let Some(metadata) = meta["metadata"].as_object() {
        ensure!(
            !metadata.keys().any(|k| k.starts_with("skill-graph-")),
            "relationship metadata requires staged annotation and renewed scan; use graph maintenance workflow"
        );
    }
    let parent = graph.parent().context("missing graph directory")?;
    let lock = parent.join(".skill-graph-lock");
    fs::create_dir(&lock)
        .context("promotion lock exists; inspect another writer or interrupted promotion")?;
    struct Lock(std::path::PathBuf);
    impl Drop for Lock {
        fn drop(&mut self) {
            let _ = fs::remove_dir(&self.0);
        }
    }
    let _lock = Lock(lock);
    let checked = bundle::check_graph(graph)?;
    let before = bundle::read_bounded(graph, 16 * 1024 * 1024)?;
    ensure!(
        serde_json::from_slice::<Value>(&before)? == checked,
        "graph changed while validating locked snapshot"
    );
    let root = checked["roots"]
        .as_array()
        .context("missing roots")?
        .iter()
        .find(|r| r["id"] == root_id)
        .context("root is not registered")?;
    let root = Path::new(root["path"].as_str().context("missing root path")?).canonicalize()?;
    let old_index = fs::read(parent.join("INDEX.md")).ok();
    let stage = tempfile::tempdir_in(&root)?;
    let (digest, files) = bundle::fingerprint(&prepared.join("bundle"))?;
    ensure!(
        accepted["fingerprint"] == digest,
        "prepared bundle changed before promotion"
    );
    bundle::snapshot(
        &prepared.join("bundle"),
        &stage.path().join("bundle"),
        &files,
    )?;
    let target = root.join(name);
    // Reserve only a fresh directory. Write resources first and publish SKILL.md last.
    fs::create_dir(&target)
        .context("install target already exists; replacements require graph maintenance")?;
    let mut published_graph: Option<Vec<u8>> = None;
    let mut published_index: Option<Vec<u8>> = None;
    let result = (|| -> Result<Value> {
        for path in files
            .keys()
            .filter(|p| p.as_str() != "SKILL.md")
            .chain(std::iter::once(&"SKILL.md".to_owned()))
        {
            let source = stage.path().join("bundle").join(path);
            let destination = target.join(path);
            fs::create_dir_all(destination.parent().context("missing target parent")?)?;
            let mut output = fs::OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(&destination)?;
            output.write_all(&bundle::read_bounded(&source, 1024 * 1024)?)?;
            output.sync_all()?;
            fs::set_permissions(&destination, fs::metadata(source)?.permissions())?;
        }
        ensure!(
            bundle::fingerprint(&target)?.0 == digest,
            "promoted bytes differ"
        );
        let roots = stage.path().join("roots.json");
        bundle::atomic_json(&roots, &json!({"roots":checked["roots"]}))?;
        let graph_stage = tempfile::tempdir_in(parent)?;
        let generated = graph_stage.path().join("generated");
        let status = Command::new(python)
            .arg(helper)
            .args(["build", "--roots"])
            .arg(&roots)
            .arg("--output")
            .arg(&generated)
            .output()?;
        fs::write(stage.path().join("build.stderr"), &status.stderr)?;
        ensure!(
            status.status.success(),
            "graph rebuild failed; target rollback required"
        );
        bundle::check_graph(&generated.join("graph.json"))?;
        ensure!(
            bundle::read_bounded(graph, 16 * 1024 * 1024)? == before,
            "concurrent graph update; promotion aborted"
        );
        let evidence = prepared.join(format!("promotion-{}", bundle::hash(&before)));
        fs::create_dir(&evidence).context("promotion evidence already exists")?;
        fs::write(evidence.join("graph.before.json"), &before)?;
        if let Some(index) = &old_index {
            fs::write(evidence.join("INDEX.before.md"), index)?;
        }
        bundle::atomic_json(
            &evidence.join("receipt.json"),
            &json!({"target":target,"fingerprint":digest,"scan":receipt,"root":root_id}),
        )?;
        let next_index = fs::read(generated.join("INDEX.md"))?;
        let next_graph = fs::read(generated.join("graph.json"))?;
        fs::rename(generated.join("INDEX.md"), parent.join("INDEX.md"))?;
        published_index = Some(next_index);
        fs::rename(generated.join("graph.json"), graph)?;
        published_graph = Some(next_graph);
        bundle::check_graph(graph)?;
        Ok(
            json!({"status":"installed","target":target,"id":format!("{root_id}/{name}"),"fingerprint":digest,"evidence":evidence}),
        )
    })();
    if result.is_err() {
        let rollback = root.join(format!(
            ".skill-search-rollback-{}-{}",
            std::process::id(),
            &digest[..12]
        ));
        fs::rename(&target, &rollback)
            .context("rollback target moved or changed; inspect reserved target manually")?;
        bundle::atomic_json(
            &prepared.join("rollback.json"),
            &json!({"path":rollback,"root":root_id,"fingerprint":digest}),
        )?;
        // Restore only our exact published bytes. Preserve concurrent graph changes.
        let current = fs::read(graph)?;
        if published_graph.as_ref() == Some(&current) {
            bundle::atomic_json(graph, &serde_json::from_slice(&before)?)?;
        }
        let current_index = fs::read(parent.join("INDEX.md")).ok();
        if published_index.is_some()
            && published_index == current_index
            && let Some(index) = old_index
        {
            fs::write(parent.join("INDEX.md"), index)?;
        }
    }
    result
}
