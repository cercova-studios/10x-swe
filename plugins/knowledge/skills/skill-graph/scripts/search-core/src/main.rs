mod bundle;
mod catalog;
mod graph_view;
mod jev;
mod promotion;
mod records;
mod registry;
mod scanner;
mod topics;

use anyhow::{Context, Result, ensure};
use clap::{Parser, Subcommand, ValueEnum};
use serde_json::{Value, json};
use std::{
    fs,
    path::{Path, PathBuf},
};

#[derive(Parser)]
#[command(
    version,
    about = "Offline skill discovery; explicit remote metadata and scanner-gated loading"
)]
struct Cli {
    #[arg(long, global = true)]
    state: Option<PathBuf>,
    #[arg(long, global = true)]
    graph: Option<PathBuf>,
    #[command(subcommand)]
    command: Operation,
}
#[derive(Clone, ValueEnum)]
enum ClassificationMode {
    Shortlist,
    Catalog,
}
#[derive(Subcommand)]
enum Operation {
    /// Emit a complete portable skills/workflows knowledge-snapshot/v2 JSONL record.
    Export {
        #[arg(long)]
        query: Option<String>,
        #[arg(long, default_value_t=5, value_parser=clap::value_parser!(u8).range(1..=20))]
        limit: u8,
    },
    /// Rebuild the unified map using the installed local BGE model.
    Map {
        #[arg(long)]
        python: Option<PathBuf>,
        #[arg(long)]
        helper: Option<PathBuf>,
    },
    /// Export a fresh portable Markdown vault; never overwrite live skills.
    Vault {
        #[arg(long)]
        output: PathBuf,
        #[arg(long)]
        include_inferred: bool,
        #[arg(long)]
        python: Option<PathBuf>,
        #[arg(long)]
        helper: Option<PathBuf>,
    },
    /// Suggest bounded skill routes; review applicability before execution.
    Path {
        query: String,
        #[arg(long, default_value_t=3, value_parser=clap::value_parser!(u8).range(1..=10))]
        limit: u8,
        /// Explicitly run the existing local embedding model for the task query.
        #[arg(long)]
        semantic: bool,
        #[arg(long)]
        python: Option<PathBuf>,
        #[arg(long)]
        helper: Option<PathBuf>,
    },
    /// Read heuristic communities from the same relationship graph.
    Clusters {
        query: Option<String>,
        #[arg(long, default_value_t=10, value_parser=clap::value_parser!(u8).range(1..=40))]
        limit: u8,
    },
    /// Inspect typed declared, observed and inferred links without loading skills.
    Related {
        id: String,
        #[arg(long, default_value_t=10, value_parser=clap::value_parser!(u8).range(1..=40))]
        limit: u8,
    },
    /// Explore recorded local skill relationships in an interactive terminal.
    Graph {
        id: Option<String>,
    },
    /// Rebuild and validate the inventory, semantic map and search catalog locally.
    Refresh {
        /// Rebuild declared relationships and lexical search without a neural model.
        #[arg(long)]
        lexical: bool,
    },
    Classify {
        query: String,
        #[arg(long, required = true)]
        allow_cloud: bool,
        #[arg(long, default_value = "shortlist")]
        mode: ClassificationMode,
        #[arg(long)]
        min_fit: f64,
    },
    Search {
        query: String,
        #[arg(long)]
        only_global: bool,
        /// Include skills.sh metadata alongside local results.
        #[arg(long, conflicts_with = "only_global")]
        remote: bool,
        #[arg(long, default_value_t=5, value_parser=clap::value_parser!(u8).range(1..=20))]
        limit: u8,
    },
    Neighbors {
        id: String,
    },
    Prepare {
        id: Option<String>,
        #[arg(long, conflicts_with = "id")]
        local: Option<PathBuf>,
    },
    Scan {
        id: String,
        #[arg(long, required = true)]
        allow_upload: bool,
    },
    Load {
        id: String,
        #[arg(long, default_value = "SKILL.md")]
        resource: String,
    },
    Install {
        id: String,
        #[arg(long)]
        root: String,
        #[arg(long)]
        graph_python: Option<PathBuf>,
        #[arg(long)]
        graph_helper: Option<PathBuf>,
    },
}
fn read_json(path: &Path) -> Result<Value> {
    Ok(serde_json::from_slice(&bundle::read_bounded(
        path,
        16 * 1024 * 1024,
    )?)?)
}
fn remote_search(state: &Path, query: &str, limit: usize) -> Result<Value> {
    let key = bundle::hash(&serde_json::to_vec(
        &json!({"adapter":"skills.sh-public-audits-v2","query":query,"limit":limit}),
    )?);
    let cache = state.join("remote-cache").join(format!("{key}.json"));
    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)?
        .as_secs();
    if cache.is_file() {
        let cached = read_json(&cache)?;
        if cached["fetched_at_unix"]
            .as_u64()
            .is_some_and(|t| t <= now && now - t < 60)
        {
            let mut result = cached["result"].clone();
            ensure!(
                result["results"]
                    .as_array()
                    .is_some_and(|a| a.len() <= limit),
                "invalid registry cache"
            );
            result["cache"] = json!("fresh");
            result["fetched_at_unix"] = cached["fetched_at_unix"].clone();
            return Ok(result);
        }
    }
    let mut result = registry::search(query, limit)?;
    bundle::atomic_json(&cache, &json!({"fetched_at_unix":now,"result":result}))?;
    result["cache"] = json!("network");
    result["fetched_at_unix"] = json!(now);
    Ok(result)
}
fn prepared(state: &Path, id: &str) -> Result<PathBuf> {
    ensure!(
        id.starts_with("p-") && id.len() == 66 && id[2..].bytes().all(|c| c.is_ascii_hexdigit()),
        "invalid prepared ID"
    );
    let path = state.join("quarantine").join(id);
    ensure!(
        path.is_dir() && !fs::symlink_metadata(&path)?.file_type().is_symlink(),
        "missing or symlinked prepared bundle"
    );
    Ok(path)
}
fn global_graph(checked: &Value) -> Result<Value> {
    let mut global = checked.clone();
    let nodes = global["nodes"]
        .as_array_mut()
        .context("missing graph nodes")?;
    nodes.retain(|node| node["scope"] == "global");
    let ids: std::collections::HashSet<String> = nodes
        .iter()
        .filter_map(|n| n["id"].as_str().map(str::to_owned))
        .collect();
    global["aliases"]
        .as_array_mut()
        .context("missing aliases")?
        .retain(|a| ids.contains(a["target"].as_str().unwrap_or("")));
    global["edges"]
        .as_array_mut()
        .context("missing edges")?
        .retain(|e| {
            ids.contains(e["source"].as_str().unwrap_or(""))
                && ids.contains(e["target"].as_str().unwrap_or(""))
        });
    Ok(global)
}

fn run(cli: Cli) -> Result<Value> {
    let home = std::env::var_os("HOME")
        .map(PathBuf::from)
        .context("HOME unavailable; specify state and graph")?;
    let root = std::env::var_os("AGENT_KNOWLEDGE_HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| home.join(".agents"));
    let state = cli
        .state
        .unwrap_or_else(|| root.join("knowledge/skills/search"));
    let graph = cli
        .graph
        .unwrap_or_else(|| root.join("knowledge/skills/graph.json"));
    let db = state.join("catalog.sqlite");
    match cli.command {
        Operation::Export { query, limit } => {
            ensure!(
                query.as_ref().is_none_or(|q| !q.trim().is_empty()
                    && q.len() <= 400
                    && !q.chars().any(char::is_control)),
                "Export query must be 1–400 bytes without controls"
            );
            let checked = bundle::check_graph(&graph)?;
            let rows = if let Some(q) = query.as_deref() {
                fs::create_dir_all(&state)?;
                catalog::refresh_checked(&checked, &db)?;
                catalog::search(&db, q, limit as usize)?["results"]
                    .as_array()
                    .context("Missing search results")?
                    .clone()
            } else {
                Vec::new()
            };
            let mut result = records::export(&checked, query.as_deref(), &rows)?;
            for node in result["nodes"].as_array_mut().unwrap() {
                node["details"]["open_with"] = json!([
                    "skill-search",
                    "--graph",
                    graph,
                    "--state",
                    state,
                    "load",
                    node["details"]["scoped_id"]
                ]);
            }
            ensure!(
                bundle::check_graph(&graph)? == checked,
                "Skill inventory changed during export; retry"
            );
            Ok(result)
        }
        Operation::Map { python, helper } => {
            let python = python.unwrap_or_else(|| root.join("runtimes/source-insights/bin/python"));
            let helper =
                helper.unwrap_or_else(|| root.join("skills/skill-graph/scripts/concepts.py"));
            topics::build_map(&graph, &state, &python, &helper)
        }
        Operation::Vault {
            output,
            include_inferred,
            python,
            helper,
        } => {
            let checked = bundle::check_graph(&graph)?;
            if include_inferred {
                topics::validate(&checked)?;
            }
            let python = python.unwrap_or_else(|| root.join("runtimes/skill-graph/bin/python"));
            let helper =
                helper.unwrap_or_else(|| root.join("skills/skill-graph/scripts/concepts.py"));
            let output = output.to_str().context("vault path requires UTF-8")?;
            let mut args = vec!["export", "--output", output];
            if include_inferred {
                args.push("--include-inferred");
            }
            topics::helper(&python, &helper, &checked, &args)
        }
        Operation::Path {
            query,
            limit,
            semantic,
            python,
            helper,
        } => {
            ensure!(
                !query.trim().is_empty() && query.len() <= if semantic { 400 } else { 4096 },
                "task query is empty or exceeds the selected retrieval byte budget"
            );
            let checked = bundle::check_graph(&graph)?;
            topics::validate(&checked)?;
            ensure!(
                semantic || (python.is_none() && helper.is_none()),
                "runtime overrides require --semantic"
            );
            let scores = if semantic {
                let python =
                    python.unwrap_or_else(|| root.join("runtimes/source-insights/bin/python"));
                let helper =
                    helper.unwrap_or_else(|| root.join("skills/skill-graph/scripts/concepts.py"));
                Some(topics::helper(
                    &python,
                    &helper,
                    &checked,
                    &["query", "--query", &query],
                )?)
            } else {
                None
            };
            topics::paths(&checked, &query, scores.as_ref(), limit as usize)
        }
        Operation::Clusters { query, limit } => topics::clusters(
            &bundle::check_graph(&graph)?,
            query.as_deref(),
            limit as usize,
        ),
        Operation::Related { id, limit } => {
            topics::related(&bundle::check_graph(&graph)?, &id, limit as usize)
        }
        Operation::Classify {
            query,
            allow_cloud,
            mode,
            min_fit,
        } => {
            ensure!(allow_cloud, "explicit cloud consent required");
            ensure!(
                min_fit.is_finite() && (0.0..=1.0).contains(&min_fit),
                "min-fit must be between zero and one"
            );
            let checked = bundle::check_graph(&graph)?;
            let global = global_graph(&checked)?;
            let candidates = match mode {
                ClassificationMode::Shortlist => {
                    let global_db = state.join("classification-catalog.sqlite");
                    catalog::refresh_checked(&global, &global_db)?;
                    catalog::search(&global_db, &query, 5)?["results"]
                        .as_array()
                        .context("missing results")?
                        .clone()
                }
                ClassificationMode::Catalog => global["nodes"].as_array().unwrap().clone(),
            };
            let metadata: Vec<Value> = candidates
                .iter()
                .filter(|n| n["kind"].as_str().unwrap_or("skill") == "skill")
                .map(|n| json!({"id":n["id"],"name":n["name"],"description":n["description"]}))
                .collect();
            jev::classify(&query, &metadata, &state, min_fit)
        }
        Operation::Graph { id } => {
            let checked = bundle::check_graph(&graph)?;
            graph_view::run(&checked, id.as_deref())?;
            Ok(Value::Null)
        }
        Operation::Refresh { lexical } => {
            ensure!(
                graph.file_name().is_some_and(|name| name == "graph.json"),
                "refresh requires a graph.json path with roots.json in the same directory"
            );
            let parent = graph.parent().context("missing graph directory")?;
            let output = std::process::Command::new(root.join("runtimes/skill-graph/bin/python"))
                .arg(root.join("skills/skill-graph/scripts/graph.py"))
                .args(["build", "--roots"])
                .arg(parent.join("roots.json"))
                .arg("--output")
                .arg(parent)
                .env("PYTHONDONTWRITEBYTECODE", "1")
                .output()
                .context("starting inventory rebuild")?;
            ensure!(
                output.status.success(),
                "inventory rebuild failed: {}{}",
                String::from_utf8_lossy(&output.stderr),
                String::from_utf8_lossy(&output.stdout)
            );
            bundle::check_graph(&graph)?;
            if !lexical {
                topics::build_map(
                    &graph,
                    &state,
                    &root.join("runtimes/source-insights/bin/python"),
                    &root.join("skills/skill-graph/scripts/concepts.py"),
                )?;
            }
            let checked = bundle::check_graph(&graph)?;
            fs::create_dir_all(&state)?;
            catalog::refresh_checked(&checked, &db)
        }
        Operation::Search {
            query,
            remote,
            limit,
            only_global,
        } => {
            let local = {
                let checked = bundle::check_graph(&graph)?;
                fs::create_dir_all(&state)?;
                if only_global {
                    let global_db = state.join("classification-catalog.sqlite");
                    catalog::refresh_checked(&global_graph(&checked)?, &global_db)?;
                    Some(catalog::search(&global_db, &query, limit as usize)?)
                } else {
                    catalog::refresh_checked(&checked, &db)?;
                    Some(catalog::search(&db, &query, limit as usize)?)
                }
            };
            let remote = if remote {
                Some(remote_search(&state, &query, limit as usize)?)
            } else {
                None
            };
            Ok(json!({"local":local,"remote":remote}))
        }
        Operation::Neighbors { id } => {
            let checked = bundle::check_graph(&graph)?;
            fs::create_dir_all(&state)?;
            catalog::refresh_checked(&checked, &db)?;
            catalog::neighbors(&db, &id)
        }
        Operation::Prepare { id, local } => {
            let quarantine = state.join("quarantine");
            fs::create_dir_all(&quarantine)?;
            let temporary = tempfile::tempdir_in(&quarantine)?;
            let folder = temporary.path().join("bundle");
            let mut provenance = if let Some(p) = local {
                let (before, files) = bundle::fingerprint(&p)?;
                bundle::snapshot(&p, &folder, &files)?;
                ensure!(
                    bundle::fingerprint(&p)?.0 == before
                        && bundle::fingerprint(&folder)?.0 == before,
                    "concurrent local copy change"
                );
                json!({"origin":"local","source_path":p.canonicalize()?,"source_fingerprint":before})
            } else {
                registry::prepare(
                    id.as_deref()
                        .context("specify remote ID or --local directory")?,
                    &folder,
                )?
            };
            if let Some(object) = provenance.as_object_mut() {
                object.remove("path");
            }
            let (fingerprint, files) = bundle::fingerprint(&folder)?;
            let identity = format!(
                "p-{}",
                bundle::hash(&serde_json::to_vec(
                    &json!({"provenance":provenance,"fingerprint":fingerprint})
                )?)
            );
            let final_path = quarantine.join(&identity);
            if final_path.exists() {
                ensure!(
                    bundle::fingerprint(&final_path.join("bundle"))?.0 == fingerprint,
                    "existing quarantine changed"
                );
                return Ok(
                    json!({"id":identity,"fingerprint":fingerprint,"files":files.len(),"cached":true,"path":final_path}),
                );
            }
            bundle::atomic_json(
                &temporary.path().join("manifest.json"),
                &json!({"schema":1,"id":identity,"provenance":provenance,"fingerprint":fingerprint,"files":files}),
            )?;
            fs::rename(temporary.path(), &final_path)?;
            Ok(
                json!({"id":identity,"fingerprint":fingerprint,"files":files.len(),"path":final_path,"classification":"quarantined"}),
            )
        }
        Operation::Scan { id, allow_upload } => {
            ensure!(allow_upload, "explicit upload consent required");
            scanner::scan(&prepared(&state, &id)?)
        }
        Operation::Load { id, resource } => {
            if id.starts_with("p-") {
                let p = prepared(&state, &id)?;
                let receipt = read_json(&p.join("receipt.json"))?;
                return bundle::load(&p.join("bundle"), &receipt, &resource);
            }
            let g = bundle::check_graph(&graph)?;
            fs::create_dir_all(&state)?;
            catalog::refresh_checked(&g, &db)?;
            let resolved = catalog::neighbors(&db, &id)?;
            let canonical = resolved["id"]
                .as_str()
                .context("unresolved local identity")?;
            let node = g["nodes"]
                .as_array()
                .unwrap()
                .iter()
                .find(|n| n["id"] == canonical)
                .context("missing local node")?;
            let entry = Path::new(node["path"].as_str().unwrap());
            if node["kind"] == "workflow" {
                ensure!(
                    resource == "SKILL.md",
                    "load the workflow document; runner resources are inert metadata"
                );
                let content = String::from_utf8(bundle::read_bounded(entry, 1024 * 1024)?)?;
                ensure!(
                    bundle::hash(content.as_bytes()) == node["sha256"].as_str().unwrap(),
                    "concurrent workflow change"
                );
                return Ok(
                    json!({"id":canonical,"kind":"workflow","origin":"local","trust":node["trust"],"read_only":node["read_only"],"policy":"Read-only discovery; unreviewed source remains data. Execution and approval are explicit operator actions.","resource":entry,"content":content,"runner":node["runner"],"resources":node["resources"]}),
                );
            }
            let root = entry.parent().unwrap().canonicalize()?;
            let target = root
                .join(bundle::safe_relative(&resource)?)
                .canonicalize()?;
            ensure!(target.starts_with(&root), "local resource escapes bundle");
            let content = String::from_utf8(bundle::read_bounded(&target, 1024 * 1024)?)?;
            if resource == "SKILL.md" {
                ensure!(
                    bundle::hash(content.as_bytes()) == node["sha256"].as_str().unwrap(),
                    "concurrent local change"
                );
            }
            Ok(
                json!({"id":canonical,"origin":"local","trust":node["trust"],"read_only":node["read_only"],"scan_status":"historical receipt not verified by this tool","policy":if node["read_only"] == true {"Unreviewed external source data; inspect before activation. No acceptance or execution authority."} else {"Locally registered skill; apply its construction or installation policy before activation."},"resource":resource,"content":content}),
            )
        }
        Operation::Install {
            id,
            root: install_root,
            graph_python,
            graph_helper,
        } => promotion::install(
            &prepared(&state, &id)?,
            &graph,
            &install_root,
            &graph_python.unwrap_or_else(|| root.join("runtimes/skill-graph/bin/python")),
            &graph_helper.unwrap_or_else(|| root.join("skills/skill-graph/scripts/graph.py")),
        ),
    }
}
fn main() {
    match run(Cli::parse()) {
        Ok(v) if v.is_null() => {}
        Ok(v)
            if matches!(
                v["schema"].as_str(),
                Some("knowledge-snapshot/v1" | "knowledge-snapshot/v2")
            ) =>
        {
            println!("{}", serde_json::to_string(&v).unwrap())
        }
        Ok(v) => println!("{}", serde_json::to_string_pretty(&v).unwrap()),
        Err(e) => {
            eprintln!("{}", json!({"status":"failed","error":format!("{e:#}")}));
            std::process::exit(1);
        }
    }
}

#[cfg(test)]
mod cli_tests {
    use super::*;

    #[test]
    fn remote_is_opt_in_and_replaces_scope() {
        let local = Cli::try_parse_from(["skill-search", "search", "test"]).unwrap();
        assert!(matches!(
            local.command,
            Operation::Search { remote: false, .. }
        ));
        let both = Cli::try_parse_from(["skill-search", "search", "test", "--remote"]).unwrap();
        assert!(matches!(
            both.command,
            Operation::Search { remote: true, .. }
        ));
        assert!(
            Cli::try_parse_from(["skill-search", "search", "test", "--scope", "both"]).is_err()
        );
        assert!(
            Cli::try_parse_from([
                "skill-search",
                "search",
                "test",
                "--remote",
                "--only-global"
            ])
            .is_err()
        );
    }

    #[test]
    fn classifier_requires_explicit_cloud_and_threshold() {
        assert!(
            Cli::try_parse_from([
                "skill-search",
                "classify",
                "public test",
                "--min-fit",
                "0.5"
            ])
            .is_err()
        );
        assert!(
            Cli::try_parse_from(["skill-search", "classify", "public test", "--allow-cloud"])
                .is_err()
        );
        assert!(
            Cli::try_parse_from([
                "skill-search",
                "classify",
                "public test",
                "--allow-cloud",
                "--min-fit",
                "0.5",
                "--mode",
                "catalog"
            ])
            .is_ok()
        );
    }
}
