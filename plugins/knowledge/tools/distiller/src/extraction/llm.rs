use std::env;
use std::time::Duration;

use anyhow::Result;
use once_cell::sync::Lazy;
use regex::Regex;
use reqwest::Client;
use serde::{Deserialize, Serialize};

use crate::extraction::checks::{passes_safety_checks, structure_noise_score};
use crate::observability;

const DEFAULT_PROVIDERS: &str = "gemma4:31b-cloud";
const DEFAULT_TIMEOUT_MS: u64 = 12_000;
const DEFAULT_MAX_INPUT_CHARS: usize = 60_000;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LlmOutcome {
    SkippedNoAcceptableCandidate,
    Applied,
}

pub async fn extract_via_llm(
    html: &str,
    source_url: &str,
    debug_enabled: bool,
    heuristic_baseline: Option<&str>,
) -> Option<String> {
    let providers = provider_list();
    if providers.is_empty() {
        return None;
    }

    let preprocessed = preprocess_html(html);
    // Prefer the already-cleaned heuristic markdown so safety gates compare like-for-like.
    let baseline_markdown = match heuristic_baseline.map(str::trim).filter(|s| !s.is_empty()) {
        Some(baseline) => baseline.to_string(),
        None => crate::markdown_ast::html_to_markdown(&preprocessed, Some(source_url)),
    };
    let baseline_score = structure_noise_score(&baseline_markdown);
    observability::debug(
        debug_enabled,
        "pipeline.llm",
        format!(
            "providers={} baseline_noise={baseline_score}",
            providers.join(",")
        ),
    );

    for provider in providers {
        let candidate = if provider.eq_ignore_ascii_case("jina") {
            run_jina_provider(source_url).await
        } else {
            run_ollama_provider(&provider, &preprocessed, source_url).await
        };
        let Ok(markdown) = candidate else {
            continue;
        };
        if markdown.trim().is_empty() {
            continue;
        }

        let candidate_score = structure_noise_score(&markdown);

        if !passes_safety_checks(&baseline_markdown, &markdown) {
            continue;
        }
        if candidate_score > baseline_score + 2 {
            continue;
        }
        observability::debug(
            debug_enabled,
            "pipeline.llm.provider",
            format!("provider={provider} accepted_noise={candidate_score}"),
        );
        return Some(markdown);
    }

    None
}

pub fn outcome_for(applied: bool) -> LlmOutcome {
    if applied {
        LlmOutcome::Applied
    } else {
        LlmOutcome::SkippedNoAcceptableCandidate
    }
}

fn provider_list() -> Vec<String> {
    let raw = env::var("DISTILLER_LLM_PROVIDERS").unwrap_or_else(|_| DEFAULT_PROVIDERS.into());
    raw.split(',')
        .map(|m| m.trim().to_string())
        .filter(|m| !m.is_empty())
        .collect()
}

fn timeout_ms() -> u64 {
    env::var("DISTILLER_LLM_TIMEOUT_MS")
        .ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or(DEFAULT_TIMEOUT_MS)
}

fn max_input_chars() -> usize {
    env::var("DISTILLER_LLM_MAX_INPUT_CHARS")
        .ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or(DEFAULT_MAX_INPUT_CHARS)
}

fn ollama_base_url() -> String {
    env::var("OLLAMA_BASE_URL").unwrap_or_else(|_| "http://127.0.0.1:11434".to_string())
}

fn client() -> Result<Client> {
    Ok(Client::builder()
        .timeout(Duration::from_millis(timeout_ms()))
        .build()?)
}

async fn run_jina_provider(source_url: &str) -> Result<String> {
    let without_scheme = source_url
        .strip_prefix("https://")
        .or_else(|| source_url.strip_prefix("http://"))
        .unwrap_or(source_url);
    let url = format!("https://r.jina.ai/http://{without_scheme}");
    let c = client()?;
    let mut req = c
        .get(url)
        .header("Accept", "text/plain, text/markdown;q=0.9, */*;q=0.8");
    if let Ok(api_key) = env::var("JINA_API_KEY") {
        if !api_key.trim().is_empty() {
            req = req.bearer_auth(api_key);
        }
    }

    let response = req.send().await?;
    if !response.status().is_success() {
        anyhow::bail!("jina provider failed: {}", response.status());
    }
    let text = response.text().await?;
    let markdown = extract_jina_markdown_payload(&text).unwrap_or(text.as_str());
    Ok(sanitize_markdown(markdown))
}

#[derive(Debug, Serialize)]
struct OllamaGenerateRequest<'a> {
    model: &'a str,
    stream: bool,
    system: &'a str,
    prompt: &'a str,
    options: OllamaOptions,
}

#[derive(Debug, Serialize)]
struct OllamaOptions {
    temperature: f32,
}

#[derive(Debug, Deserialize)]
struct OllamaGenerateResponse {
    response: Option<String>,
}

async fn run_ollama_provider(
    model: &str,
    preprocessed_html: &str,
    source_url: &str,
) -> Result<String> {
    let prompt = format!(
        "URL: {source_url}\n\nConvert the HTML below into clean markdown.\n\
Rules:\n\
- Keep factual content and links.\n\
- Remove navigation, footer, signup and related-post chrome.\n\
- Preserve headings and paragraph/list structure.\n\
- Output markdown only.\n\nHTML:\n{preprocessed_html}"
    );
    let req = OllamaGenerateRequest {
        model,
        stream: false,
        system: "You are a precise HTML to markdown extractor.",
        prompt: &prompt,
        options: OllamaOptions { temperature: 0.0 },
    };

    let url = format!("{}/api/generate", ollama_base_url());
    let response = client()?.post(url).json(&req).send().await?;
    if !response.status().is_success() {
        anyhow::bail!("ollama provider failed: {}", response.status());
    }
    let parsed: OllamaGenerateResponse = response.json().await?;
    let text = parsed
        .response
        .unwrap_or_default()
        .trim()
        .trim_start_matches("```markdown")
        .trim_start_matches("```md")
        .trim_start_matches("```")
        .trim_end_matches("```")
        .trim()
        .to_string();
    if text.is_empty() {
        anyhow::bail!("empty ollama output");
    }
    Ok(sanitize_markdown(&text))
}

static PREPROCESS_DROP_BLOCK_RE: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r"(?is)<(?:script|style|noscript|nav|footer|aside)[^>]*>.*?</(?:script|style|noscript|nav|footer|aside)>")
        .expect("valid regex")
});
static PREPROCESS_DROP_INLINE_RE: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r"(?is)<(?:header|form)[^>]*>.*?</(?:header|form)>").expect("valid regex")
});
static MULTI_WS_RE: Lazy<Regex> = Lazy::new(|| Regex::new(r"\n{3,}").expect("valid regex"));

fn preprocess_html(html: &str) -> String {
    let mut out = PREPROCESS_DROP_BLOCK_RE.replace_all(html, "\n").to_string();
    out = PREPROCESS_DROP_INLINE_RE
        .replace_all(&out, "\n")
        .to_string();
    out = MULTI_WS_RE.replace_all(&out, "\n\n").to_string();
    out.chars().take(max_input_chars()).collect()
}

fn sanitize_markdown(markdown: &str) -> String {
    crate::markdown::strip_known_chrome(markdown)
        .trim()
        .to_string()
}

fn extract_jina_markdown_payload(payload: &str) -> Option<&str> {
    payload
        .split_once("\nMarkdown Content:\n")
        .map(|(_, tail)| tail)
        .or_else(|| {
            payload
                .split_once("\nMarkdown Content:\r\n")
                .map(|(_, tail)| tail)
        })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn preprocess_strips_script_nav_footer() {
        let html = "<html><script>x</script><nav>menu</nav><article><h1>Title</h1><p>Body</p></article><footer>end</footer></html>";
        let out = preprocess_html(html);
        assert!(!out.contains("<script"));
        assert!(!out.contains("<nav"));
        assert!(!out.contains("<footer"));
        assert!(out.contains("<article>"));
    }
}
