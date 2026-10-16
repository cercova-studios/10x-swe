use once_cell::sync::Lazy;
use scraper::{Html, Selector};

use crate::constants::ENTRY_POINT_SELECTORS;
use crate::dom::count_words;
use crate::scoring::score_element;

static ARTICLE_SELECTOR: Lazy<Selector> =
    Lazy::new(|| Selector::parse("article").expect("valid selector"));
static BODY_SELECTOR: Lazy<Selector> =
    Lazy::new(|| Selector::parse("body").expect("valid selector"));

pub fn find_main_content_html(html: &Html) -> Option<String> {
    if let Some(article_html) = best_article_candidate(html) {
        return Some(article_html);
    }

    let mut candidates: Vec<(String, f64)> = Vec::new();

    for (idx, selector_str) in ENTRY_POINT_SELECTORS.iter().enumerate() {
        let selector = match Selector::parse(selector_str) {
            Ok(s) => s,
            Err(_) => continue,
        };

        for element in html.select(&selector) {
            let priority = ((ENTRY_POINT_SELECTORS.len() - idx) as f64) * 40.0;
            let content_score = score_element(&element);
            candidates.push((element.html(), priority + content_score));
        }
    }

    candidates.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
    candidates.into_iter().next().map(|c| c.0)
}

fn best_article_candidate(html: &Html) -> Option<String> {
    let mut best: Option<(String, usize)> = None;

    for article in html.select(&ARTICLE_SELECTOR) {
        let text = article.text().collect::<String>();
        let words = count_words(&text);
        if words < 40 {
            continue;
        }

        let html_snippet = article.html();
        match &best {
            Some((_, best_words)) if words <= *best_words => {}
            _ => best = Some((html_snippet, words)),
        }
    }

    best.map(|(html, _)| html)
}

pub fn body_fallback_html(html: &Html) -> Option<String> {
    html.select(&BODY_SELECTOR).next().map(|body| body.html())
}
