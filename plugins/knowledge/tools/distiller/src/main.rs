use std::fs;
use std::io::{self, Read, Write};
use std::path::PathBuf;

use anyhow::{Context, Result};
use clap::{Parser, ValueEnum};
use distiller::types::{DistillerOptions, ParseMode};
use sha2::{Digest, Sha256};

mod kfx;

#[derive(Debug, Clone, ValueEnum)]
enum OutputMode {
    Markdown,
    Json,
    Epub,
    Kfx,
}

#[derive(Debug, Parser)]
#[command(
    name = "distiller",
    about = "Extract readable content and create EPUB/KFX from web pages and PDFs"
)]
struct Cli {
    /// URL, UTF-8 HTML, or born-digital PDF (PDFs use cloud reconstruction).
    #[arg(required_unless_present = "stdin", conflicts_with = "stdin")]
    input: Option<String>,

    /// Parse UTF-8 HTML without source fetching (5 MiB); EPUB may call Muse for its mandatory cover.
    #[arg(long, requires = "base_url", conflicts_with_all = ["input", "llm", "proxy", "lang"])]
    stdin: bool,

    /// Original HTTP(S) source URL; resolves relative links and labels prepared evidence.
    #[arg(long)]
    base_url: Option<String>,

    /// Output file (default: webpage.md). Use "-" or omit with --stdout to print to stdout.
    #[arg(short, long)]
    output: Option<String>,

    /// Write output to stdout instead of a file (for piping to other tools)
    #[arg(long)]
    stdout: bool,

    /// Output mode
    #[arg(long, value_enum, default_value = "markdown")]
    mode: OutputMode,

    /// Override the mandatory Muse/local-typography EPUB cover with a local PNG/JPEG (4 MiB).
    #[arg(long)]
    cover: Option<PathBuf>,

    /// Preferred language (BCP 47)
    #[arg(short, long)]
    lang: Option<String>,

    /// Optional outbound HTTP/HTTPS proxy URL (for example: http://user:pass@host:port)
    #[arg(long)]
    proxy: Option<String>,

    /// Enable debug behavior
    #[arg(long)]
    debug: bool,

    /// Enable optional HTML extraction LLM; PDFs always use their reconstruction stage.
    #[arg(long)]
    llm: bool,

    #[arg(long, hide = true)]
    pdf_worker: bool,
}

#[tokio::main]
async fn main() -> Result<()> {
    let mut args = Cli::parse();
    let use_kfx = matches!(args.mode, OutputMode::Kfx);

    let mode = match args.mode {
        OutputMode::Markdown => ParseMode::Markdown,
        OutputMode::Json => ParseMode::Json,
        OutputMode::Epub | OutputMode::Kfx => ParseMode::Epub,
    };

    if mode == ParseMode::Epub {
        anyhow::ensure!(!args.llm && !args.stdout && args.output.as_deref() != Some("-"),
            "EPUB/KFX writes a file; --llm, --stdout and -o - are unsupported (PDF reconstruction uses its own model stage)");
    }
    anyhow::ensure!(
        args.cover.is_none() || mode == ParseMode::Epub,
        "--cover requires --mode epub or kfx"
    );
    if let Some(base) = args.base_url.as_deref() {
        anyhow::ensure!(
            base.len() <= 8192 && !base.chars().any(|c| c.is_whitespace() || c.is_control()),
            "Base URL must be at most 8192 bytes without whitespace or controls"
        );
        let url = url::Url::parse(base).context("Invalid base URL")?;
        anyhow::ensure!(
            matches!(url.scheme(), "http" | "https")
                && url.host_str().is_some()
                && url.username().is_empty()
                && url.password().is_none(),
            "Base URL must be HTTP(S) without credentials"
        );
    }

    let kfx_output = if use_kfx {
        anyhow::ensure!(
            !args.pdf_worker,
            "PDF workers only produce intermediate EPUB"
        );
        let export = kfx::Output::prepare(args.input.as_deref(), args.output.as_deref())?;
        args.output = Some(export.epub().to_string_lossy().into_owned());
        Some(export)
    } else {
        None
    };

    if let Some(input) = args.input.as_deref().filter(|p| {
        std::path::Path::new(p)
            .extension()
            .is_some_and(|ext| ext.eq_ignore_ascii_case("pdf"))
    }) {
        anyhow::ensure!(mode == ParseMode::Epub && args.base_url.is_none() && args.proxy.is_none() && args.lang.is_none(), "Local PDF input supports reconstructed EPUB/KFX only, without --base-url, --proxy or --lang");
        let input = fs::canonicalize(input).context("PDF input file does not exist")?;
        let output = args
            .output
            .map(PathBuf::from)
            .unwrap_or_else(|| input.with_extension("epub"));
        if args.pdf_worker {
            distiller::pdf::extract(&input, &output)?;
            return Ok(());
        }
        distiller::pdf::write_epub(&input, &output, args.cover.as_deref()).await?;
        if let Some(export) = kfx_output {
            export.finish().await?;
            return Ok(());
        }
        eprintln!("Wrote output to {}", output.display());
        return Ok(());
    }

    let opts = DistillerOptions {
        language: args.lang,
        proxy_url: args.proxy,
        debug: args.debug,
        llm: args.llm,
        mode,
        ..DistillerOptions::default()
    };

    let mut source = None;
    let mut local_file = None;
    let mut source_url = args.base_url.as_deref();
    let result = if args.stdin {
        let base = args.base_url.as_deref().unwrap();
        let html = read_html(io::stdin())?;
        let hash = format!("{:x}", Sha256::digest(html.as_bytes()));
        source = Some(serde_json::json!({"url": base, "sha256": hash,
                                        "media_type": "text/html", "encoding": "utf-8"}));
        distiller::parse_html(&html, Some(base), opts)
    } else {
        let input = args.input.as_deref().unwrap();
        if url::Url::parse(input).is_ok_and(|u| matches!(u.scheme(), "http" | "https")) {
            anyhow::ensure!(
                args.base_url.is_none(),
                "--base-url is only for HTML files or stdin"
            );
            source_url = Some(input);
            distiller::extract_url(input, opts).await?
        } else {
            anyhow::ensure!(
                !opts.llm && opts.proxy_url.is_none(),
                "Local HTML input cannot use --llm or --proxy"
            );
            let file = fs::canonicalize(input).context("HTML input file does not exist")?;
            let html = read_html(fs::File::open(&file)?)?;
            local_file = Some(file);
            distiller::parse_html(&html, source_url, opts)
        }
    };

    if result.word_count == 0 {
        anyhow::bail!("No content could be extracted");
    }

    if mode == ParseMode::Epub {
        let target = args.output.map(PathBuf::from).unwrap_or_else(|| {
            local_file
                .as_ref()
                .map(|p| p.with_extension("epub"))
                .unwrap_or_else(|| PathBuf::from("webpage.epub"))
        });
        tokio::time::timeout(
            std::time::Duration::from_secs(120),
            distiller::epub::write_epub(
                &result,
                source_url,
                local_file.as_ref().and_then(|p| p.parent()),
                !args.stdin,
                &target,
                args.cover.as_deref(),
            ),
        )
        .await
        .context("EPUB export exceeded the 120-second total timeout")??;
        if let Some(export) = kfx_output {
            export.finish().await?;
            return Ok(());
        }
        eprintln!("Wrote output to {}", target.display());
        return Ok(());
    }

    let output = match mode {
        ParseMode::Markdown => result.content_markdown.clone().unwrap_or_default(),
        ParseMode::Json => {
            if let Some(source) = source {
                serde_json::to_string_pretty(&serde_json::json!({
                    "schema": "article-extraction/v1", "source": source,
                    "extractor": {"name": "distiller", "version": env!("CARGO_PKG_VERSION"),
                        "method": "deterministic-html", "options": {}},
                    "document": {"title": result.title, "markdown": result.content_markdown}
                }))?
            } else {
                serde_json::to_string_pretty(&result)?
            }
        }
        ParseMode::Epub => unreachable!(),
    };

    let use_stdout =
        args.stdout || args.output.as_deref() == Some("-") || (args.stdin && args.output.is_none());

    if use_stdout {
        io::stdout()
            .write_all(output.as_bytes())
            .context("Failed to write to stdout")?;
    } else {
        let target = if let Some(path) = args.output {
            path
        } else {
            match mode {
                ParseMode::Markdown => "webpage.md".to_string(),
                ParseMode::Json => "webpage.json".to_string(),
                ParseMode::Epub => unreachable!(),
            }
        };

        fs::write(&target, &output).with_context(|| format!("Failed to write {target}"))?;
        eprintln!("Wrote output to {target}");
    }

    Ok(())
}

fn read_html(reader: impl Read) -> Result<String> {
    let mut bytes = Vec::new();
    reader.take(5 * 1024 * 1024 + 1).read_to_end(&mut bytes)?;
    anyhow::ensure!(bytes.len() <= 5 * 1024 * 1024, "HTML exceeds 5 MiB limit");
    String::from_utf8(bytes).context("HTML must be valid UTF-8")
}
