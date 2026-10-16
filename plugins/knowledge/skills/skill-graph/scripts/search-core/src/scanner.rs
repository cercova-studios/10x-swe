use crate::bundle;
use anyhow::{Context, Result, ensure};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    path::Path,
    process::{Command, Stdio},
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

pub const IMAGE: &str = "local/agent-infra-scanner@sha256:44aa4227b60652d8f77fa4e7b424d384186894bcf4c181e0d8541af52a6875e9";

pub fn classify(
    raw: &Value,
    exit: i32,
    digest: &str,
    files: &BTreeMap<String, String>,
) -> Result<Value> {
    let responses = raw["scan_path_responses"]
        .as_array()
        .context("missing scanner responses")?;
    let response = responses
        .iter()
        .find(|r| r["client"] == "/input/SKILL.md")
        .context("missing expected scanner path")?;
    let skills = response["skill_risks"]
        .as_array()
        .context("missing skill coverage")?;
    let mut covered = BTreeSet::new();
    let mut findings = BTreeSet::new();
    for skill in skills {
        for file in skill["files"].as_array().context("missing file coverage")? {
            covered.insert(
                file["name"]
                    .as_str()
                    .context("invalid scanner file")?
                    .to_owned(),
            );
        }
        for (key, _) in skill["risk_indexes"]
            .as_object()
            .context("missing risk assessment")?
        {
            findings.insert(key.clone());
        }
    }
    fn operational_error(value: &Value) -> bool {
        match value {
            Value::Object(map) => map.iter().any(|(k, v)| {
                (k.to_lowercase().contains("error")
                    && !(v.is_null()
                        || v == false
                        || v.as_array().is_some_and(|a| a.is_empty())
                        || v.as_str() == Some("")))
                    || operational_error(v)
            }),
            Value::Array(a) => a.iter().any(operational_error),
            _ => false,
        }
    }
    let missing: Vec<_> = files
        .keys()
        .filter(|p| !covered.contains(*p))
        .cloned()
        .collect();
    let complete = exit == 0
        && !skills.is_empty()
        && missing.is_empty()
        && response["server_risks"]
            .as_array()
            .is_some_and(|a| a.is_empty())
        && !operational_error(raw);
    let classification = if !complete {
        "blocked-unavailable"
    } else if findings.iter().any(|f| f != "third_party_content_exposure") {
        "rejected"
    } else {
        "accepted"
    };
    Ok(
        json!({"schema":1,"classification":classification,"fingerprint":digest,"scanner":IMAGE,"exit_code":exit,"covered_files":covered,"missing_files":missing,"findings":findings,"raw_sha256":bundle::hash(&serde_json::to_vec(raw)?),"scanned_at_unix":SystemTime::now().duration_since(UNIX_EPOCH)?.as_secs(),"mcp_executed":false,"rationale":"Only external-content exposure alone is informational under installed policy; all other findings block. No known-malicious evidence observed during this scan."}),
    )
}

pub fn scan(prepared: &Path) -> Result<Value> {
    let folder = prepared.join("bundle");
    let (digest, files) = bundle::fingerprint(&folder)?;
    let snapshot = tempfile::tempdir_in(prepared)?;
    let snapshot_bundle = snapshot.path().join("bundle");
    bundle::snapshot(&folder, &snapshot_bundle, &files)?;
    ensure!(
        std::env::var_os("SNYK_TOKEN").is_some(),
        "SNYK_TOKEN must be inherited from your secret manager; it is not persisted"
    );
    let inspect = Command::new("container")
        .args(["image", "inspect", IMAGE])
        .output()
        .context("Apple container unavailable")?;
    ensure!(
        inspect.status.success(),
        "pinned scanner image unavailable; no fallback or pull attempted"
    );
    let identity = String::from_utf8(inspect.stdout)?;
    ensure!(
        identity.contains(IMAGE.split('@').nth(1).unwrap()),
        "scanner image digest mismatch"
    );
    ensure!(
        !prepared.join("receipt.json").exists() && !prepared.join("scan.json").exists(),
        "scan evidence already exists; prepare a new bundle for another assessment"
    );
    let name = format!(
        "skill-search-{}-{}",
        std::process::id(),
        SystemTime::now().duration_since(UNIX_EPOCH)?.as_millis()
    );
    let snapshot_path = snapshot_bundle.canonicalize()?;
    ensure!(
        !snapshot_path.to_string_lossy().contains(','),
        "mount path contains comma"
    );
    let mount = format!(
        "type=bind,source={},target=/input,readonly",
        snapshot_path.display()
    );
    let stdout = tempfile::NamedTempFile::new_in(prepared)?;
    let stderr = tempfile::NamedTempFile::new_in(prepared)?;
    let mut child = Command::new("container")
        .args([
            "run",
            "--rm",
            "--name",
            &name,
            "--read-only",
            "--user",
            "65532:65532",
            "--cap-drop",
            "ALL",
            "--cpus",
            "2",
            "--memory",
            "1G",
            "--ulimit",
            "nofile=1024:1024",
            "--ulimit",
            "nproc=128:128",
            "--mount",
            "type=tmpfs,target=/tmp,size=64M,mode=1777",
            "--mount",
            &mount,
            "--env",
            "SNYK_TOKEN",
            IMAGE,
            "scan",
            "/input/SKILL.md",
            "--json",
            "--storage-file",
            "/tmp/scan-state",
        ])
        .stdout(Stdio::from(stdout.reopen()?))
        .stderr(Stdio::from(stderr.reopen()?))
        .spawn()?;
    let start = Instant::now();
    let exit = loop {
        if let Some(s) = child.try_wait()? {
            break s.code().unwrap_or(-1);
        }
        if start.elapsed() > Duration::from_secs(210) {
            let _ = Command::new("container").args(["stop", &name]).output();
            let _ = child.kill();
            let _ = child.wait();
            break -1;
        }
        std::thread::sleep(Duration::from_millis(100));
    };
    let _ = Command::new("container").args(["delete", &name]).output();
    stdout
        .persist(prepared.join("scan.json"))
        .map_err(|e| e.error)?;
    stderr
        .persist(prepared.join("scan.stderr"))
        .map_err(|e| e.error)?;
    let raw: Value = serde_json::from_slice(&bundle::read_bounded(
        &prepared.join("scan.json"),
        8 * 1024 * 1024,
    )?)
    .context("malformed scan output; evidence retained")?;
    let mut receipt = classify(&raw, exit, &digest, &files)?;
    if bundle::fingerprint(&folder)?.0 != digest
        || bundle::fingerprint(&snapshot_bundle)?.0 != digest
    {
        receipt["classification"] = json!("blocked-unavailable");
        receipt["concurrent_change"] = json!(true);
    }
    bundle::atomic_json(&prepared.join("receipt.json"), &receipt)?;
    Ok(receipt)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn raw(risks: Value) -> Value {
        json!({"scan_path_responses":[{"client":"/input/SKILL.md","server_risks":[],"skill_risks":[{"files":[{"name":"SKILL.md","type":"instruction"}],"risk_indexes":risks}]}]})
    }
    #[test]
    fn policy_and_coverage() -> Result<()> {
        let mut files = BTreeMap::from([("SKILL.md".to_owned(), "test".to_owned())]);
        assert_eq!(
            classify(&raw(json!({})), 0, "digest", &files)?["classification"],
            "accepted"
        );
        assert_eq!(
            classify(
                &raw(json!({"third_party_content_exposure":{}})),
                0,
                "digest",
                &files
            )?["classification"],
            "accepted"
        );
        assert_eq!(
            classify(&raw(json!({"prompt_injection":{}})), 0, "digest", &files)?["classification"],
            "rejected"
        );
        assert_eq!(
            classify(&raw(json!({})), 1, "digest", &files)?["classification"],
            "blocked-unavailable"
        );
        files.insert("script.rs".into(), "test".into());
        assert_eq!(
            classify(&raw(json!({})), 0, "digest", &files)?["classification"],
            "blocked-unavailable"
        );
        assert!(classify(&json!({}), 0, "digest", &files).is_err());
        Ok(())
    }
}
