//! One relationship graph: bounded topic discovery and candidate workflow paths.
use anyhow::{Context, Result, ensure};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    path::Path,
    process::{Command, Stdio},
};

/// Serialize with installation/maintenance writers, then publish one verified graph.
pub fn build_map(path: &Path, state: &Path, python: &Path, script: &Path) -> Result<Value> {
    let parent = path.parent().context("missing graph directory")?;
    let lock = parent.join(".skill-graph-lock");
    fs::create_dir(&lock)
        .context("graph writer lock exists; inspect the active/interrupted operation")?;
    struct Guard(std::path::PathBuf);
    impl Drop for Guard {
        fn drop(&mut self) {
            let _ = fs::remove_dir(&self.0);
        }
    }
    let _guard = Guard(lock);
    let checked = crate::bundle::check_graph(path)?;
    let before = crate::bundle::read_bounded(path, 16 * 1024 * 1024)?;
    ensure!(
        serde_json::from_slice::<Value>(&before)? == checked,
        "graph changed while checking snapshot"
    );
    fs::create_dir_all(state)?;
    let temp = tempfile::tempdir_in(parent)?;
    let output = temp.path().join("mapped.json");
    let cache = state.join("concepts.sqlite");
    let result = helper(
        python,
        script,
        &checked,
        &[
            "build",
            "--output",
            output.to_str().context("map path requires UTF-8")?,
            "--cache",
            cache.to_str().context("cache path requires UTF-8")?,
        ],
    )?;
    let mapped = crate::bundle::check_graph(&output)?;
    validate(&mapped)?;
    ensure!(
        crate::bundle::check_graph(path)? == checked
            && crate::bundle::read_bounded(path, 16 * 1024 * 1024)? == before,
        "concurrent graph/skill changes; map not published"
    );
    // Retained snapshot makes rollback explicit; no active skill files are changed.
    let backup = state
        .join("map-backups")
        .join(format!("{}.json", crate::bundle::hash(&before)));
    if !backup.exists() {
        crate::bundle::atomic_json(&backup, &checked)?;
    }
    let index = parent.join("INDEX.md");
    let old_index = fs::read(&index).ok();
    let mut text = format!(
        "# Skill graph\n\n{} canonical skills; {} typed relationships; {} inferred clusters.\n\nLoad selected entrypoints and useful neighbors only. Inferred links are suggestions.\n\n",
        mapped["nodes"].as_array().unwrap().len(),
        mapped["edges"]
            .as_array()
            .context("missing mapped edges")?
            .len(),
        mapped["clusters"]
            .as_array()
            .context("missing mapped clusters")?
            .len()
    );
    for node in mapped["nodes"].as_array().unwrap() {
        text.push_str(&format!(
            "- `{}` — {}\n",
            node["id"].as_str().unwrap(),
            node["description"]
                .as_str()
                .unwrap_or("")
                .replace(['\n', '\r'], " ")
                .chars()
                .take(160)
                .collect::<String>()
        ));
    }
    let index_stage = temp.path().join("INDEX.md");
    fs::write(&index_stage, text.as_bytes())?;
    fs::rename(&index_stage, &index)?;
    if let Err(error) = crate::bundle::atomic_json(path, &mapped) {
        if fs::read(&index).ok().as_deref() == Some(text.as_bytes()) {
            match old_index {
                Some(bytes) => fs::write(&index, bytes)?,
                None => fs::remove_file(&index)?,
            };
        }
        return Err(error);
    }
    Ok(
        json!({"status":"mapped","graph":path,"backup":backup,"summary":result,"meaning":"Derived relationships are suggestions; no skill acceptance or authorization changes."}),
    )
}

pub fn helper(python: &Path, helper: &Path, graph: &Value, args: &[&str]) -> Result<Value> {
    ensure!(
        python.is_file() && helper.is_file(),
        "mapping runtime/helper unavailable"
    );
    let temp = tempfile::tempdir()?;
    let input = temp.path().join("graph.json");
    fs::write(&input, serde_json::to_vec(graph)?)?;
    let stdout = temp.path().join("stdout");
    let stderr = temp.path().join("stderr");
    let mut child = Command::new(python)
        .arg(helper)
        .args(args)
        .arg("--graph")
        .arg(&input)
        .env("PYTHONDONTWRITEBYTECODE", "1")
        .stdin(Stdio::null())
        .stdout(fs::File::create(&stdout)?)
        .stderr(fs::File::create(&stderr)?)
        .spawn()?;
    let started = std::time::Instant::now();
    let status = loop {
        let oversized =
            fs::metadata(&stdout)?.len() > 1024 * 1024 || fs::metadata(&stderr)?.len() > 128 * 1024;
        if oversized || started.elapsed() > std::time::Duration::from_secs(180) {
            let _ = child.kill();
            let _ = child.wait();
            anyhow::bail!("mapping helper exceeded time/output budget");
        }
        if let Some(status) = child.try_wait()? {
            break status;
        }
        std::thread::sleep(std::time::Duration::from_millis(50));
    };
    let output = crate::bundle::read_bounded(&stdout, 1024 * 1024)?;
    let errors = crate::bundle::read_bounded(&stderr, 128 * 1024)?;
    ensure!(
        status.success(),
        "mapping helper failed: {}",
        String::from_utf8_lossy(&errors)
    );
    serde_json::from_slice(&output).context("invalid mapping helper response")
}

pub fn validate(graph: &Value) -> Result<()> {
    ensure!(
        graph["concepts"]["status"] == "fresh",
        "topic map unavailable; run skill-search map"
    );
    let nodes = graph["nodes"].as_array().context("missing nodes")?;
    let records = graph["concepts"]["records"]
        .as_array()
        .context("missing mapping provenance")?;
    ensure!(
        nodes.len() == records.len(),
        "mapping inventory changed; rebuild map"
    );
    let mut actual = BTreeMap::new();
    let mut seen = BTreeSet::new();
    for node in nodes {
        let id = node["id"].as_str().context("missing node identity")?;
        let hash = node["sha256"].as_str().context("missing node hash")?;
        ensure!(
            actual.insert(id, hash).is_none(),
            "duplicate mapped identity"
        );
    }
    for r in records {
        let id = r["id"].as_str().context("missing provenance identity")?;
        let hash = r["entrypoint_sha256"]
            .as_str()
            .context("missing provenance hash")?;
        ensure!(
            seen.insert(id) && actual.get(id) == Some(&hash),
            "mapping input changed or duplicate provenance; rebuild map"
        );
    }
    Ok(())
}
fn node_metadata(node: &Value) -> Value {
    json!({"id":node["id"],"name":node["name"],"description":node["description"],"scope":node["scope"],"path":node["path"],"cluster":node["cluster"],"secondary_clusters":node["secondary_clusters"],"bridge_score":node["bridge_score"]})
}
fn resolve<'a>(graph: &'a Value, id: &str) -> Result<&'a Value> {
    let nodes = graph["nodes"].as_array().context("missing nodes")?;
    let canonical = graph["aliases"]
        .as_array()
        .into_iter()
        .flatten()
        .find(|a| a["id"] == id)
        .and_then(|a| a["target"].as_str())
        .unwrap_or(id);
    if let Some(node) = nodes.iter().find(|n| n["id"] == canonical) {
        return Ok(node);
    }
    let found: Vec<_> = nodes.iter().filter(|n| n["name"] == id).collect();
    ensure!(
        found.len() == 1,
        "unknown or ambiguous skill; use a scoped ID"
    );
    Ok(found[0])
}

pub fn related(graph: &Value, id: &str, limit: usize) -> Result<Value> {
    let selected = resolve(graph, id)?;
    let id = selected["id"].as_str().unwrap();
    let nodes = graph["nodes"].as_array().unwrap();
    let mut links = Vec::new();
    for edge in graph["edges"].as_array().context("missing edges")? {
        let other = if edge["source"] == id {
            Some((&edge["target"], "outgoing"))
        } else if edge["target"] == id {
            Some((&edge["source"], "incoming"))
        } else {
            None
        };
        if let Some((target, direction)) = other
            && let Some(node) = nodes.iter().find(|n| n["id"] == *target)
        {
            links.push(json!({"skill":node_metadata(node),"relation":edge["relation"],"status":edge.get("status").cloned().unwrap_or(json!("declared")),"weight_hint":edge.get("weight").cloned().unwrap_or(json!(1.0)),"provenance":edge.get("provenance").cloned().unwrap_or(json!("frontmatter")),"direction":if edge["relation"]=="related" {"undirected"}else{direction}}));
        }
    }
    links.sort_by(|a, b| {
        b["weight_hint"]
            .as_f64()
            .unwrap_or(0.)
            .total_cmp(&a["weight_hint"].as_f64().unwrap_or(0.))
            .then(a["skill"]["id"].as_str().cmp(&b["skill"]["id"].as_str()))
    });
    links.truncate(limit);
    Ok(
        json!({"id":id,"connections":links,"meaning":"Typed relationships guide discovery; inferred links are suggestions and grant no permissions."}),
    )
}

fn words(query: &str) -> BTreeSet<String> {
    query
        .to_lowercase()
        .split(|c: char| !c.is_alphanumeric())
        .filter(|v| {
            v.len() > 2
                && !matches!(
                    *v,
                    "the"
                        | "and"
                        | "for"
                        | "with"
                        | "from"
                        | "that"
                        | "this"
                        | "skill"
                        | "skills"
                        | "task"
                        | "using"
                        | "use"
                )
        })
        .map(str::to_owned)
        .collect()
}
pub fn ranks(graph: &Value, query: &str, semantic: Option<&Value>) -> Result<Vec<(String, f64)>> {
    ensure!(
        !query.trim().is_empty() && query.len() <= 4096,
        "task query requires1–4096UTF-8bytes"
    );
    let nodes = graph["nodes"].as_array().context("missing nodes")?;
    if let Some(scores) = semantic {
        let rows = scores.as_array().context("invalid semantic scores")?;
        ensure!(
            rows.len() == nodes.len(),
            "semantic score coverage mismatch"
        );
        let mut seen = BTreeSet::new();
        let mut result = Vec::new();
        for row in rows {
            let id = row["id"].as_str().context("missing scored identity")?;
            let score = row["score"].as_f64().context("missing similarity")?;
            ensure!(
                score.is_finite()
                    && (-1.01..=1.01).contains(&score)
                    && nodes.iter().any(|n| n["id"] == id)
                    && seen.insert(id),
                "invalid semantic score identity/value"
            );
            result.push((id.to_owned(), score));
        }
        result.sort_by(|a, b| b.1.total_cmp(&a.1).then(a.0.cmp(&b.0)));
        return Ok(result);
    }
    let tokens = words(query);
    let docs: Vec<_> = nodes
        .iter()
        .map(|n| {
            words(&format!(
                "{} {}",
                n["name"].as_str().unwrap_or(""),
                n["description"].as_str().unwrap_or("")
            ))
        })
        .collect();
    let mut result = Vec::new();
    for (i, n) in nodes.iter().enumerate() {
        let score = tokens
            .iter()
            .filter(|t| docs[i].contains(*t))
            .map(|t| {
                let count = docs.iter().filter(|d| d.contains(t)).count();
                ((nodes.len() + 1) as f64 / (count + 1) as f64).ln()
            })
            .sum::<f64>();
        if score > 0. {
            result.push((n["id"].as_str().unwrap().to_owned(), score));
        }
    }
    result.sort_by(|a, b| b.1.total_cmp(&a.1).then(a.0.cmp(&b.0)));
    Ok(result)
}

pub fn clusters(graph: &Value, query: Option<&str>, limit: usize) -> Result<Value> {
    validate(graph)?;
    let clusters = graph["clusters"].as_array().context("missing clusters")?;
    let ranked = if let Some(query) = query {
        ranks(graph, query, None)?
    } else {
        Vec::new()
    };
    let scores: BTreeMap<_, _> = ranked
        .iter()
        .map(|(id, score)| (id.as_str(), *score))
        .collect();
    let mut result: Vec<_> = clusters
        .iter()
        .filter_map(|c| {
            let members = c["members"].as_array()?;
            let score = members
                .iter()
                .filter_map(|i| scores.get(i.as_str()?))
                .copied()
                .fold(0., f64::max);
            if query.is_some() && score == 0. {
                return None;
            }
            Some((score, c.clone()))
        })
        .collect();
    result.sort_by(|a, b| {
        b.0.total_cmp(&a.0).then(
            b.1["members"]
                .as_array()
                .unwrap()
                .len()
                .cmp(&a.1["members"].as_array().unwrap().len()),
        )
    });
    result.truncate(limit);
    Ok(
        json!({"query":query,"total_clusters":clusters.len(),"clusters":result.into_iter().map(|(score,mut c)|{c["score_hint"]=json!(score);c}).collect::<Vec<_>>(),"method":graph["concepts"]["method"],"meaning":"Heuristic communities of the unified graph, not reviewed taxonomic facts."}),
    )
}

pub fn paths(graph: &Value, query: &str, semantic: Option<&Value>, limit: usize) -> Result<Value> {
    validate(graph)?;
    let ranked = ranks(graph, query, semantic)?;
    let nodes = graph["nodes"].as_array().unwrap();
    let mut paths = Vec::new();
    let cutoff = if semantic.is_some() {
        0.65
    } else {
        ranked.first().map_or(0., |v| v.1 * 0.60)
    };
    let task_scores: BTreeMap<_, _> = ranked.iter().cloned().collect();
    for (id, score) in ranked.into_iter().filter(|v| v.1 >= cutoff).take(limit) {
        let node = nodes.iter().find(|n| n["id"] == id).unwrap();
        let connections = related(graph, &id, 16384)?;
        let mut steps = vec![
            json!({"skill":node_metadata(node),"role":"candidate primary workflow","score_hint":score,"check":"Read this entrypoint and verify task applicability before choosing this route."}),
        ];
        let mut seen = BTreeSet::from([id.clone()]);
        let mut extensions = connections["connections"].as_array().unwrap().clone();
        extensions.sort_by(|a, b| {
            task_scores
                .get(b["skill"]["id"].as_str().unwrap())
                .copied()
                .unwrap_or(0.)
                .total_cmp(
                    &task_scores
                        .get(a["skill"]["id"].as_str().unwrap())
                        .copied()
                        .unwrap_or(0.),
                )
        });
        for link in &extensions {
            let skill = &link["skill"];
            let target = skill["id"].as_str().unwrap();
            if skill["name"] == node["name"] {
                continue;
            }
            if !seen.insert(target.to_owned()) {
                continue;
            }
            let explicit_use = extensions.iter().any(|e| {
                e["skill"]["id"] == target
                    && e["relation"] == "uses"
                    && e["direction"] == "outgoing"
            });
            let relevance = task_scores.get(target).copied().unwrap_or(0.);
            if relevance >= cutoff && relevance > 0. {
                let mut relationship = link.clone();
                relationship.as_object_mut().unwrap().remove("skill");
                steps.push(json!({"skill":skill,"role":if explicit_use {"conditional workflow dependency"}else{"optional extension candidate"},"relationship":relationship,"score_hint":relevance,"check":"Read the linked skill's conditions; keep it only if it adds a necessary capability."}));
            }
            if steps.len() >= 5 {
                break;
            }
        }
        let conditional_routes:Vec<_>=extensions.iter().filter(|e|e["relation"]=="uses"&&e["direction"]=="outgoing").map(|e|json!({"id":e["skill"]["id"],"path":e["skill"]["path"],"check":"Read the entrypoint's use condition; this route is not automatically required."})).collect();
        let alternatives: Vec<_> = nodes
            .iter()
            .filter(|n| n["name"] == node["name"] && n["id"] != node["id"])
            .map(node_metadata)
            .collect();
        paths.push(json!({"entrypoint":id,"cluster":node["cluster"],"steps":steps,"conditional_routes":conditional_routes,"alternative_implementations":alternatives}));
    }
    Ok(
        json!({"task":query,"method":if semantic.is_some(){"local_bge_seed_plus_typed_graph"}else{"lexical_seed_plus_typed_graph"},"candidate_paths":paths,"score_cutoff_hint":cutoff,"planning_protocol":["Identify the deliverable, constraints and completion checks.","Read candidate entrypoints; reject inapplicable routes and check conditional dependencies.","Choose the smallest set that covers the requested capabilities. Prefer existing local skills and avoid duplicated guidance.","Use related links and cluster bridges for missing capabilities; verify every extension against its entrypoint.","Order prerequisites before dependents, resolve conflicts and cycles, and verify the result against completion checks."],"limitations":["Candidates are not globally optimal or validated executable plans.","Cosine0.65 and lexical60%-of-best cutoffs are uncalibrated heuristics, not probabilities.","Novel related links suggest extensions; cycles and optional skills do not become mandatory steps.","No path executes, delegates, uploads or grants scan acceptance."]}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn typed_paths_do_not_execute_or_turn_similarity_into_dependency() {
        let graph = json!({"nodes":[{"id":"global/a","name":"animation","description":"animate math","sha256":"a"},{"id":"global/b","name":"evidence","description":"cited math evidence","sha256":"b"}],"aliases":[],"edges":[{"source":"global/a","target":"global/b","relation":"related","status":"inferred","weight":0.8}],"clusters":[{"id":"c","members":["global/a","global/b"]}],"concepts":{"status":"fresh","records":[{"id":"global/a","entrypoint_sha256":"a"},{"id":"global/b","entrypoint_sha256":"b"}]}});
        let result = paths(&graph, "animate math cited", None, 1).unwrap();
        assert_eq!(
            result["candidate_paths"][0]["steps"][1]["role"],
            "optional extension candidate"
        );
        assert_eq!(
            result["candidate_paths"][0]["steps"][1]["relationship"]["status"],
            "inferred"
        );
        assert!(paths(&graph, "", None, 1).is_err());
        assert_eq!(
            paths(&graph, "animate math", None, 1).unwrap()["candidate_paths"][0]["steps"]
                .as_array()
                .unwrap()
                .len(),
            1
        );
        let mut stale = graph.clone();
        stale["nodes"][0]["sha256"] = json!("changed");
        assert!(validate(&stale).is_err());
    }
}
