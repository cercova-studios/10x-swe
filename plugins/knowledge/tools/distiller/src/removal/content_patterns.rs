use once_cell::sync::Lazy;
use regex::Regex;
use scraper::{ElementRef, Selector};

use crate::dom_ops::{
    contains_technical_content, detach_nodes, parse_fragment, serialize_fragment,
    sort_shallow_first,
};

static BOILERPLATE_LINE_RE: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r"(?i)^\s*(this (article|story)|originally published|copyright|all rights reserved)")
        .expect("valid regex")
});
static SHARE_ARTICLE_RE: Lazy<Regex> =
    Lazy::new(|| Regex::new(r"(?i)\bshare this article\b").expect("valid regex"));
static IMAGE_HINT_RE: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r"(?i)\bpress enter or click to view image in full size\b").expect("valid regex")
});
static SHORT_CHROME: &[&str] = &[
    "sign up",
    "sign in",
    "get app",
    "write",
    "search",
    "follow",
    "listen",
    "share",
    "top highlight",
];

static BLOCK_SEL: Lazy<Selector> = Lazy::new(|| {
    Selector::parse("p, div, section, aside, footer, span, li").expect("valid selector")
});
static NEWSLETTER_SEL: Lazy<Selector> =
    Lazy::new(|| Selector::parse("p, div, section, aside, footer").expect("valid selector"));

pub fn remove_content_patterns(input: &str) -> String {
    let mut doc = parse_fragment(input);
    let mut ids = Vec::new();

    for el in doc.select(&BLOCK_SEL) {
        if contains_technical_content(&el) {
            continue;
        }
        let text = normalized_text(&el);
        if text.is_empty() {
            continue;
        }
        let lower = text.to_ascii_lowercase();

        if SHORT_CHROME.iter().any(|chrome| lower == *chrome) {
            ids.push(el.id());
            continue;
        }
        if IMAGE_HINT_RE.is_match(&text) {
            ids.push(el.id());
            continue;
        }
        if SHARE_ARTICLE_RE.is_match(&text) && text.len() < 80 {
            ids.push(el.id());
            continue;
        }
        if BOILERPLATE_LINE_RE.is_match(&text) && text.len() < 200 {
            ids.push(el.id());
            continue;
        }
        if matches!(text.as_str(), "·" | "!") {
            ids.push(el.id());
            continue;
        }
    }

    for el in doc.select(&NEWSLETTER_SEL) {
        if contains_technical_content(&el) {
            continue;
        }
        let text = normalized_text(&el);
        let lower = text.to_ascii_lowercase();
        if lower.contains("subscribe")
            && (lower.contains("newsletter") || lower.contains("email"))
            && text.len() < 280
        {
            ids.push(el.id());
        }
    }

    sort_shallow_first(&doc, &mut ids);
    detach_nodes(&mut doc, ids);

    serialize_fragment(&doc)
}

fn normalized_text(el: &ElementRef<'_>) -> String {
    el.text()
        .collect::<String>()
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
}

#[cfg(test)]
mod tests {
    use super::remove_content_patterns;

    #[test]
    fn removes_short_ui_chrome_blocks() {
        let html = "<p>Sign up</p><p>Follow</p><p>Real content paragraph.</p>";
        let cleaned = remove_content_patterns(html);
        assert!(!cleaned.to_lowercase().contains("sign up"));
        assert!(!cleaned.to_lowercase().contains("follow"));
        assert!(cleaned.contains("Real content paragraph."));
    }

    #[test]
    fn removes_image_hint_and_standalone_counters() {
        let html =
            "<p>Press enter or click to view image in full size</p><p>1</p><p>!</p><p>Body text</p>";
        let cleaned = remove_content_patterns(html);
        assert!(!cleaned.to_lowercase().contains("press enter or click"));
        assert!(cleaned.contains("Body text"));
    }
}
