use once_cell::sync::Lazy;
use regex::Regex;
use scraper::Html;

use super::{chat_llm, github, hackernews, reddit, substack, x_twitter, youtube};

#[derive(Debug, Clone, Default)]
pub struct ExtractorResult {
    pub content_html: String,
    pub title: Option<String>,
    pub description: Option<String>,
    pub author: Option<String>,
    pub published: Option<String>,
    pub site: Option<String>,
}

pub fn run_extractors(html: &Html, url: &str) -> Option<ExtractorResult> {
    for entry in EXTRACTORS.iter() {
        if entry.matches(url) {
            if let Some(result) = (entry.sync_extract)(html, url) {
                return Some(result);
            }
        }
    }
    None
}

#[derive(Clone)]
enum UrlPattern {
    Domain(&'static str),
    Regex(&'static Lazy<Regex>),
}

impl UrlPattern {
    fn matches(&self, url: &str) -> bool {
        match self {
            UrlPattern::Domain(domain) => url::Url::parse(url)
                .ok()
                .and_then(|u| {
                    u.host_str()
                        .map(|h| h == *domain || h.ends_with(&format!(".{domain}")))
                })
                .unwrap_or(false),
            UrlPattern::Regex(re) => re.is_match(url),
        }
    }
}

struct ExtractorEntry {
    patterns: Vec<UrlPattern>,
    sync_extract: fn(&Html, &str) -> Option<ExtractorResult>,
}

impl ExtractorEntry {
    fn matches(&self, url: &str) -> bool {
        self.patterns.iter().any(|p| p.matches(url))
    }
}

static SUBSTACK_PATH_RE: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r"^https?://[^/]*substack\.com/(p|@[^/]+/note)/").expect("valid regex")
});

static EXTRACTORS: Lazy<Vec<ExtractorEntry>> = Lazy::new(|| {
    vec![
        ExtractorEntry {
            patterns: vec![
                UrlPattern::Domain("substack.com"),
                UrlPattern::Regex(&SUBSTACK_PATH_RE),
            ],
            sync_extract: substack::extract,
        },
        ExtractorEntry {
            patterns: vec![UrlPattern::Domain("reddit.com")],
            sync_extract: reddit::extract,
        },
        ExtractorEntry {
            patterns: vec![UrlPattern::Domain("github.com")],
            sync_extract: github::extract,
        },
        ExtractorEntry {
            patterns: vec![UrlPattern::Domain("news.ycombinator.com")],
            sync_extract: hackernews::extract,
        },
        ExtractorEntry {
            patterns: vec![
                UrlPattern::Domain("x.com"),
                UrlPattern::Domain("twitter.com"),
            ],
            sync_extract: x_twitter::extract,
        },
        ExtractorEntry {
            patterns: vec![
                UrlPattern::Domain("youtube.com"),
                UrlPattern::Domain("youtu.be"),
            ],
            sync_extract: youtube::extract,
        },
        ExtractorEntry {
            patterns: vec![
                UrlPattern::Domain("chatgpt.com"),
                UrlPattern::Domain("claude.ai"),
                UrlPattern::Domain("grok.com"),
                UrlPattern::Domain("gemini.google.com"),
            ],
            sync_extract: chat_llm::extract,
        },
    ]
});
