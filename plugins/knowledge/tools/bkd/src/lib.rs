mod capture;
mod connectors;
#[cfg(test)]
mod database_tests;
mod embedding;
mod graph;
mod importer;
mod index;
mod knowledge;
mod lexical;
mod model;
mod passage;
mod reader;
mod render;
mod search;
mod state;
mod store;
mod tui;
mod ui;
use anyhow::{Result, ensure};
use clap::{Args, Parser, Subcommand};
use serde_json::{Value, json};
use std::{
    io::{self, BufReader, IsTerminal},
    path::PathBuf,
};

#[derive(Parser)]
#[command(
    version,
    about = "Local bookmark search, relationship maps and reviewed public imports"
)]
struct Cli {
    #[arg(long, global = true)]
    home: Option<PathBuf>,
    #[arg(long, global = true)]
    json: bool,
    /// Read explicit knowledge snapshots (v1 or skills/workflows v2) from a file or '-' (stdin).
    #[arg(long, global = true)]
    records: Option<PathBuf>,
    /// Open a destination-bound plan for deliberate review in the default terminal UI.
    #[arg(long)]
    plan: Option<PathBuf>,
    /// Use keyword ranking in the default terminal UI.
    #[arg(long)]
    lexical_only: bool,
    #[command(subcommand)]
    command: Option<Cmd>,
}
#[derive(Args, Clone)]
struct Filters {
    #[arg(long="source",value_delimiter=',',value_parser=model::PROVIDERS)]
    sources: Vec<String>,
    #[arg(long="kind",value_delimiter=',',value_parser=model::KINDS)]
    kinds: Vec<String>,
    /// Include this domain and its subdomains; never suffix lookalikes.
    #[arg(long)]
    domain: Option<String>,
}
impl Filters {
    fn filter(&self) -> Result<search::Filter> {
        let mut f = search::Filter {
            sources: self.sources.clone(),
            kinds: self.kinds.clone(),
            domain: self.domain.clone(),
        };
        f.validate()?;
        Ok(f)
    }
}
#[derive(Subcommand)]
enum Cmd {
    /// Store a bearer token or database URL in the OS credential store, read from stdin.
    Auth {
        #[arg(value_parser=["instapaper","raindrop","neon"])]
        provider: String,
        #[arg(long, default_value = "default")]
        account: String,
    },
    /// Refresh remote snapshots and build missing local vectors. No remote writes.
    Sync {
        #[arg(long="source",value_delimiter=',',value_parser=["instapaper","raindrop","neon"])]
        sources: Vec<String>,
        #[arg(long)]
        lexical_only: bool,
        /// Build missing vectors from cached data without contacting connectors.
        #[arg(long, conflicts_with_all = ["sources", "lexical_only"])]
        offline: bool,
    },
    /// Print the best bookmark URL. Use --list for ranked results.
    Search {
        query: String,
        #[command(flatten)]
        filters: Filters,
        #[arg(long, default_value_t = 20)]
        limit: usize,
        #[arg(long)]
        lexical_only: bool,
        #[arg(long)]
        no_graph: bool,
        /// Show the ranked list instead of only the best URL.
        #[arg(long)]
        list: bool,
        #[arg(long)]
        rich: bool,
    },
    Graph {
        #[command(flatten)]
        filters: Filters,
        #[arg(long)]
        /// Include slower whole-library inferred similarity suggestions.
        similarity: bool,
    },
    Related {
        id: String,
        #[command(flatten)]
        filters: Filters,
    },
    Path {
        a: String,
        b: String,
        #[command(flatten)]
        filters: Filters,
    },
    Relate {
        a: String,
        b: String,
        #[arg(long)]
        remove: bool,
        #[arg(long)]
        suppress_similarity: bool,
    },
    /// Inspect a bookmark or knowledge node with source coverage and citations.
    Inspect {
        id: String,
    },
    /// Record a local revision-pinned skill→insight or bookmark→entry link.
    LinkKnowledge {
        a: String,
        b: String,
        #[arg(long)]
        reason: Option<String>,
        #[arg(long, conflicts_with = "remove")]
        reviewed: bool,
        #[arg(long)]
        remove: bool,
    },
    /// Portable origin-preserving JSONL, or an authored-relationship artifact.
    Export {
        #[command(flatten)]
        filters: Filters,
        #[arg(long)]
        relationships: bool,
    },
    /// Preview and select bookmarks before publishing URL/title to rsnair.tech.
    Import {
        file: Option<PathBuf>,
        #[command(flatten)]
        filters: Filters,
        /// Semantic review criterion, e.g. 'research blog posts'. Every structural candidate is shown.
        #[arg(long)]
        query: Option<String>,
        #[arg(long)]
        plan: Option<PathBuf>,
        #[arg(long, conflicts_with = "apply")]
        dry_run: bool,
        #[arg(long)]
        apply: bool,
        /// Required plan checksum for noninteractive publication.
        #[arg(long, requires = "apply")]
        approve: Option<String>,
        #[arg(long, requires = "plan", value_delimiter = ',')]
        select: Vec<String>,
        #[arg(long)]
        lexical_only: bool,
        /// Restore authored relationships; does not publish bookmark URLs/titles.
        #[arg(long,requires="file",conflicts_with_all=["query","plan","approve","select"])]
        relationships: bool,
    },
    /// Publish one URL/title after a deliberate confirmation.
    Save {
        url: String,
        #[arg(long, default_value = "")]
        title: String,
        #[arg(long,value_parser=model::KINDS)]
        kind: Option<String>,
    },
    Retry {
        #[arg(long)]
        apply: bool,
    },
    Kinds,
    Doctor,
    Model,
    /// Optional loopback browser with rich Markdown and drag/drop saving.
    Ui {
        #[arg(long)]
        no_open: bool,
    },
    /// Validate and ingest a portable fixture into the local cache.
    Index {
        file: PathBuf,
        #[arg(long)]
        lexical_only: bool,
    },
}
fn store(home: &std::path::Path) -> Result<store::Store> {
    store::Store::new(state::credential(home, "neon")?)
}
fn input(path: &std::path::Path) -> Result<Box<dyn io::BufRead>> {
    if path == std::path::Path::new("-") {
        ensure!(
            !io::stdin().is_terminal(),
            "Pipe records to stdin or provide a file"
        );
        Ok(Box::new(BufReader::new(io::stdin())))
    } else {
        Ok(Box::new(BufReader::new(std::fs::File::open(path)?)))
    }
}
fn snapshot_graph(
    db: &mut rusqlite::Connection,
    filter: &search::Filter,
    similar: bool,
) -> Result<graph::Graph> {
    let tx = db.transaction()?;
    let books = filter.books(&tx)?;
    let g = graph::derive(&tx, &books, similar)?;
    tx.rollback()?;
    Ok(g)
}
fn run(cli: &Cli) -> Result<Value> {
    let config = cli
        .records
        .as_ref()
        .map(|p| knowledge::Config::read(input(p)?))
        .transpose()?
        .unwrap_or_default();
    run_with_records(cli, &config)
}
fn run_with_records(cli: &Cli, knowledge_config: &knowledge::Config) -> Result<Value> {
    if cli.command.is_none() {
        ensure!(
            !cli.json && io::stdout().is_terminal() && io::stdin().is_terminal(),
            "TUI requires a terminal; use search/graph --json for agents"
        );
    }
    let home = cli.home.clone().unwrap_or_else(state::home);
    state::prepare(&home)?;
    let Some(command) = &cli.command else {
        capture::run(
            &home,
            knowledge_config,
            knowledge_config.enabled(),
            search::Filter::default(),
            cli.lexical_only,
            cli.plan.as_deref(),
        )?;
        return Ok(Value::Null);
    };
    ensure!(
        cli.plan.is_none() && !cli.lexical_only,
        "Place command options after the command"
    );
    let include_knowledge = knowledge_config.enabled();
    ensure!(
        !include_knowledge
            || matches!(
                command,
                Cmd::Search { .. }
                    | Cmd::Graph { .. }
                    | Cmd::Inspect { .. }
                    | Cmd::Related { .. }
                    | Cmd::Path { .. }
                    | Cmd::LinkKnowledge { .. }
                    | Cmd::Ui { .. }
            ),
        "--records applies only to search, graph, inspect, related, path, link-knowledge or UI"
    );
    match command {
        Cmd::Kinds => return Ok(json!({"kinds":model::KINDS})),
        Cmd::Model => {
            return Ok(
                json!({"path":embedding::path(),"sha256":embedding::MODEL_SHA,"spec":embedding::SPEC,"runtime":"llama-embedding","enabled":"on semantic indexing/search","winnow":"optional follow-up; not auto-started"}),
            );
        }
        Cmd::Auth { provider, account } => {
            let secret = state::secret_stdin()?;
            state::auth(&home, provider, account, secret.trim())?;
            return Ok(json!({"configured":provider,"account":account}));
        }
        _ => {}
    }
    let mut db = state::db(&home)?;
    match command {
        Cmd::Sync {
            sources,
            lexical_only,
            offline,
        } => {
            let sources = if *offline {
                Vec::new()
            } else if sources.is_empty() {
                vec!["instapaper".into(), "raindrop".into(), "neon".into()]
            } else {
                sources.clone()
            };
            let revision = index::revision(&db)?;
            let mut snapshots = Vec::new();
            let mut failed = Vec::new();
            let mut relations = None;
            for provider in sources {
                match connectors::snapshot(&home, &provider) {
                    Ok((account, records, links)) => {
                        if links.is_some() {
                            relations = links;
                        }
                        snapshots.push((provider, account, records));
                    }
                    Err(e) => failed.push(json!({"provider":provider,"error":e.to_string()})),
                }
            }
            let count = if snapshots.is_empty() && !offline {
                state::records(&db)?.len()
            } else {
                index::publish(
                    &mut db,
                    &snapshots,
                    revision,
                    !lexical_only,
                    relations.as_deref(),
                )?
            };
            if !failed.is_empty() {
                anyhow::bail!(
                    "Sync incomplete; successful snapshots retained, failed sources preserved: {}",
                    serde_json::to_string(&failed)?
                );
            }
            Ok(
                json!({"origins":count,"refreshed":snapshots.iter().map(|(p,_,_)|p).collect::<Vec<_>>(),"indexed":!lexical_only,"generation":index::revision(&db)?}),
            )
        }
        Cmd::Search {
            query,
            filters,
            limit,
            lexical_only,
            no_graph,
            list,
            rich,
        } => {
            let url_only = !cli.json && !list && !rich;
            let external = if include_knowledge && !url_only {
                Some(knowledge::Snapshot::load(&home, knowledge_config)?)
            } else {
                None
            };
            let combined = external
                .as_ref()
                .map(|s| knowledge::search(s, knowledge_config, query, *limit))
                .transpose()?;
            let result = search::search(
                &mut db,
                query,
                &filters.filter()?,
                *limit,
                !lexical_only,
                !no_graph,
            )?;
            if url_only {
                let hit = result
                    .hits
                    .first()
                    .ok_or_else(|| anyhow::anyhow!("No matching bookmarks"))?;
                println!("{}", hit.book.url);
                return Ok(Value::Null);
            }
            if let Some(mut combined) = combined {
                combined["bookmarks"] = serde_json::to_value(&result.hits)?;
                combined["generation"] = json!(result.generation);
                combined["strategy"] = json!(result.strategy);
                combined["passage_index"] = json!(result.passage_index);
                let g = external.as_ref().unwrap().enrich(
                    &home,
                    graph::bookmarks(result.generation, result.hits.iter().map(|h| &h.book)),
                )?;
                let ids = result.hits.iter().map(|h| h.book.id.clone()).collect();
                knowledge::contextualize(&mut combined, &g, &ids, *limit);
                if !cli.json {
                    print_combined(&combined, *rich && io::stdout().is_terminal());
                    return Ok(Value::Null);
                }
                return Ok(combined);
            }
            if !cli.json {
                for h in &result.hits {
                    if *rich && io::stdout().is_terminal() {
                        println!(
                            "\x1b[1m{}. {}\x1b[0m\n{}\n{} · {}\n{}",
                            h.rank,
                            model::clean(&h.book.title),
                            h.book.url,
                            h.book.kind,
                            h.book.sources().into_iter().collect::<Vec<_>>().join(", "),
                            render::terminal(
                                &h.book
                                    .origins
                                    .iter()
                                    .map(|r| r.note.as_str())
                                    .collect::<Vec<_>>()
                                    .join("\n")
                            )
                        );
                    } else {
                        println!(
                            "{}\t{}\t{}\t{}",
                            h.rank,
                            h.book.kind,
                            model::clean(&h.book.title).replace('\n', " "),
                            h.book.url
                        );
                    }
                }
                return Ok(Value::Null);
            }
            Ok(
                json!({"results":result.hits,"generation":result.generation,"total":result.total,"strategy":result.strategy,"passage_index":result.passage_index}),
            )
        }
        Cmd::Graph {
            filters,
            similarity,
        } => {
            let mut graph = snapshot_graph(&mut db, &filters.filter()?, *similarity)?;
            if include_knowledge {
                graph = knowledge::Snapshot::load(&home, knowledge_config)?.enrich(&home, graph)?;
            }
            if cli.json {
                Ok(serde_json::to_value(graph)?)
            } else {
                tui::run(graph)?;
                Ok(Value::Null)
            }
        }
        Cmd::Related { id, filters } => {
            if include_knowledge {
                let detail = knowledge::Snapshot::load(&home, knowledge_config)?.inspect(
                    &mut db,
                    &home,
                    &filters.filter()?,
                    id,
                )?;
                return Ok(
                    json!({"id":id,"neighbors":detail["relationships"],"generation":detail["generation"],"knowledge":detail["knowledge"]}),
                );
            }
            let g = snapshot_graph(&mut db, &filters.filter()?, true)?;
            Ok(json!({"id":id,"neighbors":g.neighbors(id),"generation":g.generation}))
        }
        Cmd::Path { a, b, filters } => {
            let mut g = snapshot_graph(&mut db, &filters.filter()?, true)?;
            if include_knowledge {
                g = knowledge::Snapshot::load(&home, knowledge_config)?.enrich(&home, g)?;
            }
            let mut result = json!({"path":g.path(a,b),"generation":g.generation});
            if let Some(knowledge) = g.knowledge {
                result["knowledge"] = knowledge;
            }
            Ok(result)
        }
        Cmd::Inspect { id } => {
            if include_knowledge {
                let s = knowledge::Snapshot::load(&home, knowledge_config)?;
                return s.inspect(&mut db, &home, &search::Filter::default(), id);
            }
            let g = snapshot_graph(&mut db, &search::Filter::default(), true)?;
            let book = filters_all(&db)?
                .into_iter()
                .find(|b| b.id == *id)
                .ok_or_else(|| {
                    anyhow::anyhow!("Unknown bookmark; supply --records FILE|- for knowledge nodes")
                })?;
            Ok(
                json!({"bookmark":book,"relationships":g.adjacent(id).into_iter().map(|(_,e)|e).collect::<Vec<_>>()}),
            )
        }
        Cmd::LinkKnowledge {
            a,
            b,
            reason,
            reviewed,
            remove,
        } => {
            ensure!(
                include_knowledge || *remove,
                "Supply --records FILE|- containing the reviewed endpoints"
            );
            if !*remove && !a.starts_with("skill:") {
                ensure!(
                    filters_all(&db)?.iter().any(|book| book.id == *a),
                    "Unknown bookmark endpoint"
                );
            }
            knowledge::Snapshot::load(&home, knowledge_config)?.review_link(
                &home,
                a,
                b,
                reason.as_deref().unwrap_or(""),
                *remove,
                *reviewed,
            )
        }
        Cmd::Relate {
            a,
            b,
            remove,
            suppress_similarity,
        } => {
            let books = filters_all(&db)?;
            ensure!(
                books.iter().any(|x| x.id == *a) && books.iter().any(|x| x.id == *b),
                "Unknown relationship endpoint"
            );
            let kind = if *suppress_similarity {
                "similar"
            } else {
                "related"
            };
            store(&home)?.write_relation(a, b, kind, *remove, *suppress_similarity)?;
            graph::relate(&mut db, a, b, kind, *remove, *suppress_similarity)?;
            Ok(json!({"confirmed":true,"generation":index::revision(&db)?}))
        }
        Cmd::Export {
            filters,
            relationships,
        } => {
            if *relationships {
                let mut q =
                    db.prepare("SELECT a,b,kind,suppressed FROM relations ORDER BY a,b,kind")?;
                let rows=q.query_map([],|r|Ok(json!({"a":r.get::<_,String>(0)?,"b":r.get::<_,String>(1)?,"kind":r.get::<_,String>(2)?,"suppressed":r.get::<_,bool>(3)?})))?;
                Ok(
                    json!({"schema":1,"relationships":rows.collect::<std::result::Result<Vec<_>,_>>()?}),
                )
            } else {
                let tx = db.transaction()?;
                for book in filters.filter()?.books(&tx)? {
                    for record in book.origins {
                        println!("{}", serde_json::to_string(&record)?);
                    }
                }
                tx.rollback()?;
                Ok(Value::Null)
            }
        }
        Cmd::Index { file, lexical_only } => {
            let records = state::jsonl(input(file)?)?;
            let mut groups =
                std::collections::BTreeMap::<(String, String), Vec<model::Record>>::new();
            for r in records {
                groups
                    .entry((r.provider.clone(), r.account.clone()))
                    .or_default()
                    .push(r);
            }
            let snapshots: Vec<_> = groups.into_iter().map(|((p, a), r)| (p, a, r)).collect();
            let mut seen = std::collections::BTreeSet::new();
            ensure!(
                snapshots.iter().all(|(p, _, _)| seen.insert(p)),
                "One account per provider per cache"
            );
            let rev = index::revision(&db)?;
            let count = index::publish(&mut db, &snapshots, rev, !lexical_only, None)?;
            Ok(json!({"origins":count}))
        }
        Cmd::Import {
            file,
            filters,
            query,
            plan,
            dry_run,
            apply,
            approve,
            select,
            lexical_only,
            relationships,
        } => {
            if *relationships {
                let destination = if *apply { Some(store(&home)?) } else { None };
                return importer::import_relationships(
                    input(file.as_ref().unwrap())?,
                    destination.as_ref(),
                    *apply,
                );
            }
            let store = store(&home)?;
            let mut review: importer::Plan = if let Some(path) =
                plan.as_ref().filter(|p| p.exists())
            {
                state::read_json(path)?
            } else {
                let f = filters.filter()?;
                let books = if let Some(file) = file {
                    index::merge(
                        state::jsonl(input(file)?)?,
                        &f.sources,
                        &f.kinds,
                        f.domain.as_deref(),
                    )
                } else {
                    f.books(&db)?
                };
                let mut evidence = json!({});
                if let Some(q) = query {
                    ensure!(
                        file.is_none(),
                        "Use bkd index before semantic review of a file"
                    );
                    for hit in search::search(&mut db, q, &f, 10000, !lexical_only, true)?.hits {
                        evidence[&hit.book.id] = json!({"rank":hit.rank,"cosine":hit.cosine,"matched_by":hit.matched_by,"graph_path":hit.graph_path});
                    }
                }
                importer::preview(
                    books,
                    json!({"filters":f,"query":query,"note":"semantic candidates require review; no research-post correctness claim"}),
                    &store,
                    evidence,
                )?
            };
            ensure!(
                review.destination == store.identity,
                "Review belongs to another destination"
            );
            if !select.is_empty() {
                let valid = review
                    .candidates
                    .iter()
                    .map(|c| model::hash(&c.url))
                    .collect::<std::collections::BTreeSet<_>>();
                ensure!(
                    select.iter().all(|id| valid.contains(id)),
                    "Unknown selected bookmark ID"
                );
                for c in &mut review.candidates {
                    c.selected = select.contains(&model::hash(&c.url));
                }
                review.selected()?;
            }
            if *dry_run || cli.json && !*apply || !io::stdin().is_terminal() && !*apply {
                if let Some(path) = plan {
                    state::write_json(path, &review)?;
                }
                return Ok(
                    json!({"plan_id":review.id()?,"plan":review,"next":"Review candidates, select exact IDs with --plan PATH --select ID,... --dry-run; then --plan PATH --apply --approve PLAN_ID"}),
                );
            }
            let approved = if let Some(id) = approve {
                ensure!(
                    *apply && plan.is_some(),
                    "Noninteractive approval requires an existing plan"
                );
                id.clone()
            } else {
                ensure!(
                    io::stdin().is_terminal() && io::stderr().is_terminal() && !cli.json,
                    "Noninteractive publication requires a reviewed plan and --approve PLAN_ID"
                );
                if !importer::review(&mut review, &mut io::stdin().lock(), &mut io::stderr())? {
                    return Ok(json!({"cancelled":true,"writes":0}));
                }
                if let Some(path) = plan {
                    state::write_json(path, &review)?;
                }
                review.id()?
            };
            importer::apply(&home, &review, &approved, &store)
        }
        Cmd::Save { url, title, kind } => {
            ensure!(
                io::stdin().is_terminal() && io::stderr().is_terminal() && !cli.json,
                "Noninteractive saves use bkd import --plan with explicit approval"
            );
            let mut r = model::Record::new(
                "manual",
                &state::account(&home, "neon")?,
                &model::hash(url),
                url,
            )?;
            r.title = title.clone();
            if let Some(k) = kind {
                r.kind = k.clone();
                r.kind_source = "manual".into();
            }
            r.validate()?;
            let store = store(&home)?;
            let mut p = importer::preview(
                index::merge(vec![r], &[], &[], None),
                json!({"action":"save"}),
                &store,
                json!({}),
            )?;
            if !importer::review(&mut p, &mut io::stdin().lock(), &mut io::stderr())? {
                return Ok(json!({"cancelled":true}));
            }
            importer::apply(&home, &p, &p.id()?, &store)
        }
        Cmd::Retry { apply } => {
            ensure!(
                *apply,
                "Use --apply to retry previously approved destination-bound batches"
            );
            Ok(json!({"retried_batches":importer::retry(&home,&store(&home)?)?}))
        }
        Cmd::Doctor => Ok(
            json!({"home":home,"origins":state::records(&db)?.len(),"generation":index::revision(&db)?,"model_exists":embedding::path().exists(),"pending_batches":std::fs::read_dir(home.join("pending")).map(|i|i.count()).unwrap_or(0),"production":"not configured by this command"}),
        ),
        Cmd::Ui { no_open } => {
            ensure!(
                !cli.json,
                "Browser mode is interactive; use search/graph --json for agents"
            );
            ui::run(&home, !*no_open, knowledge_config, include_knowledge)?;
            Ok(Value::Null)
        }
        _ => unreachable!(),
    }
}
fn print_combined(value: &Value, rich: bool) {
    for (key, label) in [
        ("bookmarks", "Bookmarks"),
        ("insights", "Inspected knowledge"),
        ("skills", "Skills"),
        ("sessions", "Sessions"),
    ] {
        println!("{label}");
        for r in value[key].as_array().into_iter().flatten() {
            let node = &r["node"];
            let title = if key == "bookmarks" {
                &r["title"]
            } else {
                &node["label"]
            };
            let id = if key == "bookmarks" {
                &r["id"]
            } else {
                &node["id"]
            };
            println!(
                "{}\t{}\t{}",
                r["rank"],
                model::clean(title.as_str().unwrap_or("")).replace('\n', " "),
                id.as_str().unwrap_or("")
            );
            if rich {
                let markdown = if key == "bookmarks" {
                    r["origins"]
                        .as_array()
                        .into_iter()
                        .flatten()
                        .filter_map(|o| o["note"].as_str())
                        .collect::<Vec<_>>()
                        .join("\n")
                } else {
                    title.as_str().unwrap_or("").to_owned()
                };
                println!("{}", render::terminal(&markdown));
            }
            if let Some(method) = r["method"].as_str() {
                println!("Retrieval: {method}");
            }
            if key == "insights" {
                println!(
                    "Coverage: {}\nCitations: {}\nCaveats: {}",
                    node["details"]["coverage"],
                    node["details"]["evidence"],
                    node["details"]["caveats"]
                );
            }
        }
    }
    println!(
        "{}",
        value["ranking"].as_str().unwrap_or("Separate corpus ranks")
    );
    let omitted = value["linked_context"]["omitted_insights"]
        .as_u64()
        .unwrap_or(0)
        + value["linked_context"]["omitted_skills"]
            .as_u64()
            .unwrap_or(0);
    if omitted > 0 {
        println!("{omitted} linked results omitted by the limit; graph/related retains them.");
    }
    println!(
        "Inspect supplied nodes with bkd --records FILE inspect ID. Links and handoff metadata never grant execution authority."
    );
}
fn filters_all(db: &rusqlite::Connection) -> Result<Vec<index::Book>> {
    search::Filter::default().books(db)
}
pub fn main() {
    let cli = Cli::parse();
    match run(&cli) {
        Ok(value) => {
            if !value.is_null() {
                if cli.json {
                    println!("{}", json!({"schema":1,"ok":true,"data":value}));
                } else {
                    println!("{}", serde_json::to_string_pretty(&value).unwrap());
                }
            }
        }
        Err(error) => {
            let message = error.to_string();
            let progress = error
                .downcast_ref::<importer::ImportFailure>()
                .map(|e| &e.progress);
            if cli.json {
                println!(
                    "{}",
                    json!({"schema":1,"ok":false,"error":model::clean(&message),"progress":progress})
                );
            } else {
                eprintln!("bkd: {}", model::clean(&message));
                if let Some(progress) = progress {
                    eprintln!("{}", serde_json::to_string_pretty(progress).unwrap());
                }
            }
            std::process::exit(1);
        }
    }
}
