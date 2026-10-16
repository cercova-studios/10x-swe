use scraper::{Html, Selector};
use url::Url;

use super::registry::ExtractorResult;

pub fn extract(html: &Html, url: &str) -> Option<ExtractorResult> {
    if !is_x_url(url) {
        return None;
    }

    let tweet_text_selector = Selector::parse("[data-testid='tweetText']").ok()?;
    let mut blocks = Vec::new();
    for node in html.select(&tweet_text_selector) {
        let text = node.text().collect::<String>().trim().to_string();
        if !text.is_empty() {
            blocks.push(format!("<p>{text}</p>"));
        }
    }
    if !blocks.is_empty() {
        return Some(ExtractorResult {
            content_html: blocks.join("\n"),
            site: Some("X".to_string()),
            ..ExtractorResult::default()
        });
    }

    let selectors = ["article", "main"];
    let content_html = best_candidate_html(html, &selectors, 20)?;
    Some(ExtractorResult {
        content_html,
        site: Some("X".to_string()),
        ..ExtractorResult::default()
    })
}

fn is_x_url(url: &str) -> bool {
    Url::parse(url)
        .ok()
        .and_then(|u| {
            u.host_str().map(|h| {
                h == "x.com"
                    || h.ends_with(".x.com")
                    || h == "twitter.com"
                    || h.ends_with(".twitter.com")
            })
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
