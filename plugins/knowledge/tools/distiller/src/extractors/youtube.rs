use scraper::{Html, Selector};
use url::Url;

use super::registry::ExtractorResult;

pub fn extract(html: &Html, url: &str) -> Option<ExtractorResult> {
    if !is_youtube_url(url) {
        return None;
    }

    let mut chunks = Vec::new();
    let title_sel = Selector::parse("meta[property='og:title']").ok()?;
    if let Some(title_meta) = html.select(&title_sel).next() {
        if let Some(title) = title_meta.value().attr("content") {
            if !title.trim().is_empty() {
                chunks.push(format!("<h1>{}</h1>", title.trim()));
            }
        }
    }

    let desc_selectors = [
        "#description-inline-expander",
        "#description",
        "ytd-watch-metadata",
    ];
    for selector in desc_selectors {
        let sel = match Selector::parse(selector) {
            Ok(s) => s,
            Err(_) => continue,
        };
        for node in html.select(&sel) {
            let text = node.text().collect::<String>();
            if text.split_whitespace().count() >= 20 {
                chunks.push(node.html());
            }
        }
        if chunks.len() > 1 {
            break;
        }
    }

    if chunks.is_empty() {
        return None;
    }

    Some(ExtractorResult {
        content_html: chunks.join("\n"),
        site: Some("YouTube".to_string()),
        ..ExtractorResult::default()
    })
}

fn is_youtube_url(url: &str) -> bool {
    Url::parse(url)
        .ok()
        .and_then(|u| {
            u.host_str().map(|h| {
                h == "youtube.com"
                    || h.ends_with(".youtube.com")
                    || h == "youtu.be"
                    || h.ends_with(".youtu.be")
            })
        })
        .unwrap_or(false)
}
