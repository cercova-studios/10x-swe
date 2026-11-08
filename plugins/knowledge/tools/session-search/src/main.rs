mod adapters;
mod embed;
mod model;
mod records;
mod search;
mod store;
mod text;
mod turns;
use anyhow::{Context, Result, ensure};
use clap::{Args, CommandFactory, Parser, Subcommand};
use serde_json::json;
use std::{collections::BTreeMap, ffi::OsString, path::PathBuf};
use store::Store;

#[derive(Parser)]
#[command(
    version,
    about = "Search local public conversation text with bounded provenance-preserving exports."
)]
struct Cli {
    #[command(subcommand)]
    command: Operation,
}
#[derive(Args)]
struct QueryArgs {
    #[arg(num_args=1..,required=true)]
    query: Vec<String>,
    #[arg(long,default_value="auto",value_parser=["auto","naive","semantic","onto"])]
    mode: String,
    #[arg(long,value_parser=clap::builder::PossibleValuesParser::new(adapters::CHOICES))]
    agent: Option<String>,
    #[arg(long, help = "e.g. 14d, 24h, or ISO timestamp")]
    since: Option<String>,
    #[arg(long)]
    json: bool,
}
#[derive(Args)]
struct SearchArgs {
    #[command(flatten)]
    query: QueryArgs,
    #[arg(long, default_value_t = 10)]
    limit: i64,
}
#[derive(Subcommand)]
enum Operation {
    /// Explicitly index selected harness stores; Amp may query its installed CLI.
    Index {
        #[arg(long,value_parser=clap::builder::PossibleValuesParser::new(adapters::CHOICES))]
        agent: Option<String>,
        #[arg(
            long,
            help = "Rebuild embeddings and insights from the existing session index"
        )]
        enrich_only: bool,
        #[arg(long)]
        json: bool,
    },
    /// Search the existing index without creating or upgrading it.
    Search(SearchArgs),
    /// Emit one bounded knowledge-snapshot/v1 JSONL record.
    Export {
        #[command(flatten)]
        args: SearchArgs,
        #[arg(long,value_parser=["user","assistant","tool"],help="Filter exported excerpts; session ranking is unchanged")]
        role: Option<String>,
    },
    /// Most recent matching session.
    Last(QueryArgs),
    /// Print one indexed session.
    Show {
        agent: String,
        session_id: String,
        #[arg(long)]
        json: bool,
    },
    /// Inspect index state without initializing it.
    Status {
        #[arg(long)]
        json: bool,
    },
}
fn db_path() -> Result<PathBuf> {
    if let Some(p) = std::env::var_os("SESSION_SEARCH_DB").filter(|s| !s.is_empty()) {
        let path = PathBuf::from(p);
        let text = path.to_string_lossy();
        return Ok(if text == "~" {
            adapters::home()?
        } else if let Some(s) = text.strip_prefix("~/") {
            adapters::home()?.join(s)
        } else {
            path
        });
    }
    if let Some(prefix) = std::env::var_os("AGENT_KNOWLEDGE_HOME") {
        return Ok(PathBuf::from(prefix).join("state/session-search.sqlite"));
    }
    if let Ok(exe) = std::env::current_exe()
        && let Some(prefix) = exe
            .parent()
            .filter(|p| p.file_name().is_some_and(|n| n == "native"))
            .and_then(|p| p.parent())
            .filter(|p| p.file_name().is_some_and(|n| n == "libexec"))
            .and_then(|p| p.parent())
            .filter(|p| p.join(".knowledge-owner.json").is_file())
    {
        return Ok(prefix.join("state/session-search.sqlite"));
    }
    Ok(adapters::home()?.join(".local/share/session-search/index.db"))
}
fn print_json(v: &impl serde::Serialize) -> Result<()> {
    println!("{}", serde_json::to_string_pretty(v)?);
    Ok(())
}
fn fmt_time(ms: i64) -> String {
    if ms == 0 {
        return "?".into();
    }
    chrono::DateTime::from_timestamp_millis(ms)
        .map(|t| {
            t.with_timezone(&chrono::Local)
                .format("%Y-%m-%d %H:%M")
                .to_string()
        })
        .unwrap_or_else(|| "?".into())
}
fn query(args: QueryArgs, limit: i64, last: bool, export: bool, role: Option<&str>) -> Result<i32> {
    let text = args.query.join(" ").trim().to_owned();
    ensure!(!text.is_empty(), "empty query");
    ensure!(
        (1..=20).contains(&limit) && text.len() <= 400,
        "Query must be at most 400 bytes and limit 1–20"
    );
    let store = Store::open(&db_path()?, false)?;
    store.conn.execute_batch("BEGIN")?;
    ensure!(
        store.count("sessions")? > 0,
        "Index empty; run session-search index explicitly"
    );
    let q = search::Query {
        text: &text,
        agent: args.agent.as_deref().map(adapters::resolve),
        since: text::since(args.since.as_deref()),
        limit: limit as usize,
        last,
    };
    let mut result = match search::run(&store, q, &args.mode) {
        Ok(v) => v,
        Err(e) => {
            if let Some(e) = e.downcast_ref::<model::StrategyUnavailable>() {
                if args.json && !export {
                    print_json(&json!({"error":e.1,"mode":e.0}))?
                } else {
                    eprintln!("{e}")
                }
                return Ok(2);
            }
            return Err(e);
        }
    };
    for hit in &mut result.hits {
        let rec = store
            .get(&hit.agent, &hit.native_id)?
            .context("Selected session changed; retry query")?;
        hit.citations = turns::excerpts(&rec, &text, None);
    }
    if export {
        if result.hits.is_empty() {
            eprintln!("No sessions found; no record exported");
            return Ok(1);
        }
        println!(
            "{}",
            serde_json::to_string(&records::export(&store, &result, role)?)?
        );
        return Ok(0);
    }
    if args.json {
        print_json(&result)?
    } else {
        let skipped = result
            .strategies_skipped
            .iter()
            .map(|(k, v)| format!("{k} ({v})"))
            .collect::<Vec<_>>()
            .join(", ");
        println!(
            "mode={} used={}{}",
            result.mode,
            result.strategies_used.join(","),
            if skipped.is_empty() {
                String::new()
            } else {
                format!(" skipped={skipped}")
            }
        );
        if result.hits.is_empty() {
            println!("no hits")
        }
        for hit in &result.hits {
            if last {
                println!(
                    "agent:    {}\nsession:  {}\nwhen:     {}\ncwd:      {}\ntitle:    {}\nstrategy: {}\nsnippet:  {}",
                    hit.agent,
                    hit.native_id,
                    fmt_time(hit.updated_at),
                    hit.cwd,
                    hit.title,
                    hit.strategy,
                    hit.snippet
                )
            } else {
                println!(
                    "\n{:10} {}  {}\n  {}",
                    hit.agent,
                    fmt_time(hit.updated_at),
                    hit.cwd,
                    hit.title
                );
                if !hit.snippet.is_empty() {
                    println!("  {}", hit.snippet)
                }
            }
        }
    }
    Ok(if result.hits.is_empty() { 1 } else { 0 })
}
fn run(cli: Cli) -> Result<i32> {
    match cli.command {
        Operation::Search(a) => query(a.query, a.limit, false, false, None),
        Operation::Export { args, role } => {
            query(args.query, args.limit, false, true, role.as_deref())
        }
        Operation::Last(a) => query(a, 1, true, false, None),
        Operation::Index {
            agent,
            enrich_only,
            json: as_json,
        } => {
            let path = db_path()?;
            let mut store = Store::open(&path, true)?;
            if enrich_only {
                let (sessions, embeddings, insights) = store.enrich(agent.as_deref())?;
                if as_json {
                    print_json(
                        &json!({"db":path,"enrich":{"embeddings":embeddings,"insights":insights},"sessions":sessions}),
                    )?
                } else {
                    println!(
                        "enriched {sessions} sessions  embeddings={embeddings} insights={insights}"
                    )
                }
                return Ok(0);
            }
            let names = agent
                .as_deref()
                .map(|a| vec![adapters::resolve(a)])
                .unwrap_or_else(|| adapters::AGENTS.to_vec());
            let mut counts = BTreeMap::new();
            let mut errors = BTreeMap::new();
            for name in names {
                match adapters::crawl(name) {
                    Ok(records) => {
                        let n = store.replace(name, records)?;
                        counts.insert(name, n);
                        if name == "agy" {
                            store.replace("gemini", vec![])?;
                        }
                    }
                    Err(e) => {
                        counts.insert(name, 0);
                        errors.insert(name, e.to_string());
                    }
                }
            }
            if errors.is_empty() {
                store.set_meta(
                    "indexed_at",
                    &chrono::Utc::now().to_rfc3339_opts(chrono::SecondsFormat::Micros, false),
                )?;
            }
            let total = counts.values().sum::<usize>();
            if as_json {
                print_json(&json!({"db":path,"counts":counts,"errors":errors,"total":total}))?
            } else {
                for (name, count) in &counts {
                    println!(
                        "{name:10} {count}{}",
                        errors
                            .get(name)
                            .map(|e| format!("  error: {e}"))
                            .unwrap_or_default()
                    );
                }
                println!("{:10} {total}", "total");
            }
            Ok(if errors.is_empty() { 0 } else { 1 })
        }
        Operation::Show {
            agent,
            session_id,
            json: as_json,
        } => {
            let path = db_path()?;
            if !path.is_file() {
                eprintln!("not found");
                return Ok(1);
            }
            let store = Store::open(&path, false)?;
            let Some(rec) = store.get(&agent, &session_id)? else {
                eprintln!("not found");
                return Ok(1);
            };
            if as_json {
                print_json(
                    &json!({"id":rec.id(),"agent":rec.agent,"native_id":rec.native_id,"cwd":rec.cwd,"title":rec.title,"summary":rec.summary,"snippet":text::snippet(if !rec.body.is_empty(){&rec.body}else if !rec.summary.is_empty(){&rec.summary}else{&rec.title},"",240),"updated_at":rec.updated_at,"source_path":rec.source_path}),
                )?
            } else {
                println!(
                    "agent:    {}\nsession:  {}\nwhen:     {}\ncwd:      {}\ntitle:    {}\nsource:   {}\n\n{}",
                    rec.agent,
                    rec.native_id,
                    fmt_time(rec.updated_at),
                    rec.cwd,
                    rec.title,
                    rec.source_path,
                    text::snippet(
                        if !rec.summary.is_empty() {
                            &rec.summary
                        } else if !rec.body.is_empty() {
                            &rec.body
                        } else {
                            &rec.title
                        },
                        "",
                        800
                    )
                )
            }
            Ok(0)
        }
        Operation::Status { json: as_json } => {
            let path = db_path()?;
            let mut payload = json!({"db":path,"exists":path.exists(),"indexed_at":null,"embedder":null,"total":0,"embeddings":0,"insights":0,"counts":{}});
            if path.exists() {
                let store = Store::open(&path, false)?;
                store.conn.execute_batch("BEGIN")?;
                payload["indexed_at"] = json!(store.meta("indexed_at")?);
                payload["embedder"] = json!(store.meta("embedder")?);
                payload["total"] = json!(store.count("sessions")?);
                payload["embeddings"] = json!(store.count("embeddings")?);
                payload["insights"] = json!(store.count("insights")?);
                for row in store
                    .conn
                    .prepare("SELECT agent,COUNT(*) FROM sessions GROUP BY agent ORDER BY agent")?
                    .query_map([], |r| Ok((r.get::<_, String>(0)?, r.get::<_, i64>(1)?)))?
                {
                    let (agent, n) = row?;
                    payload["counts"][agent] = json!(n);
                }
            }
            if as_json {
                print_json(&payload)?
            } else {
                println!(
                    "db:         {}\nindexed_at: {}\nembedder:   {}\ntotal:      {}\nembeddings: {}\ninsights:   {}",
                    path.display(),
                    payload["indexed_at"].as_str().unwrap_or("(never)"),
                    payload["embedder"].as_str().unwrap_or("(none)"),
                    payload["total"],
                    payload["embeddings"],
                    payload["insights"]
                );
                for (name, n) in payload["counts"].as_object().unwrap() {
                    println!("  {name:10} {n}")
                }
            }
            Ok(0)
        }
    }
}
fn normalized() -> Vec<OsString> {
    let mut argv = std::env::args_os().collect::<Vec<_>>();
    if argv.len() == 1 || matches!(argv[1].to_str(), Some("-h" | "--help" | "-V" | "--version")) {
        return argv;
    }
    if let Some(pos) = argv.iter().skip(1).position(|a| {
        ["index", "search", "last", "show", "status", "export"]
            .iter()
            .any(|s| a == s)
    }) {
        let command = argv.remove(pos + 1);
        argv.insert(1, command)
    } else {
        argv.insert(1, "search".into())
    }
    argv
}
fn main() {
    let argv = normalized();
    if argv.len() == 1 {
        let _ = Cli::command().print_help();
        println!();
        std::process::exit(2)
    }
    let cli = Cli::parse_from(argv);
    let code = match run(cli) {
        Ok(code) => code,
        Err(e) => {
            eprintln!("ERROR: {e}");
            2
        }
    };
    std::process::exit(code)
}
