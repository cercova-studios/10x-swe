use scraper::{Html, Selector};
use url::Url;

use super::registry::ExtractorResult;

pub fn extract(html: &Html, url: &str) -> Option<ExtractorResult> {
    if !is_github_url(url) {
        return None;
    }

    let selectors = [
        "article.markdown-body",
        "div#readme article",
        "div.markdown-body",
        "div.TimelineItem-body",
    ];
    let content_html = best_candidate_html(html, &selectors, 30)?;
    Some(ExtractorResult {
        content_html,
        site: Some("GitHub".to_string()),
        ..ExtractorResult::default()
    })
}

fn is_github_url(url: &str) -> bool {
    Url::parse(url)
        .ok()
        .and_then(|u| {
            u.host_str()
                .map(|h| h == "github.com" || h.ends_with(".github.com"))
        })
        .unwrap_or(false)
}

fn best_candidate_html(html: &Html, selectors: &[&str], min_words: usize) -> Option<String> {
    let mut best: Option<(usize, String)> = None;
    for selector in selectors {
        let sel = Selector::parse(selector).ok()?;
        for node in html.select(&sel) {
            let text = node.text().collect::<String>();
            let words = text.split_whitespace().count();
            if words < min_words {
                continue;
            }
            let snippet = node.html();
            match &best {
                Some((best_words, _)) if words <= *best_words => {}
                _ => best = Some((words, snippet)),
            }
        }
    }
    best.map(|(_, h)| h)
}
