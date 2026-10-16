use regex::Regex;
use scraper::{Html, Selector};
use serde_json::Value;
use url::Url;

use super::registry::ExtractorResult;

pub fn extract(html: &Html, url: &str) -> Option<ExtractorResult> {
    if !is_substack_url(url) {
        return None;
    }

    if let Some(result) = extract_from_rendered_dom(html) {
        return Some(result);
    }
    extract_from_preload_script(html)
}

fn is_substack_url(url: &str) -> bool {
    Url::parse(url)
        .ok()
        .and_then(|u| {
            u.host_str()
                .map(|h| h == "substack.com" || h.ends_with(".substack.com"))
        })
        .unwrap_or(false)
}

fn extract_from_rendered_dom(html: &Html) -> Option<ExtractorResult> {
    let selector = Selector::parse("div.body.markup").expect("valid selector");
    let mut best: Option<(String, usize)> = None;
    for node in html.select(&selector) {
        let text = node.text().collect::<String>();
        let words = text.split_whitespace().count();
        if words < 30 {
            continue;
        }
        let snippet = node.html();
        match &best {
            Some((_, best_words)) if words <= *best_words => {}
            _ => best = Some((snippet, words)),
        }
    }
    best.map(|(content_html, _)| ExtractorResult {
        content_html,
        site: Some("Substack".to_string()),
        ..ExtractorResult::default()
    })
}

fn extract_from_preload_script(html: &Html) -> Option<ExtractorResult> {
    let script_sel = Selector::parse("script").expect("valid selector");
    for script in html.select(&script_sel) {
        let text = script.text().collect::<String>();
        if !text.contains("window._preloads") || !text.contains("body_html") {
            continue;
        }
        let decoded = decode_json_parse_literal(&text)?;
        let data: Value = serde_json::from_str(&decoded).ok()?;
        let post = data
            .pointer("/feedData/initialPost/post")
            .or_else(|| data.pointer("/post"))
            .or_else(|| data.pointer("/initialPost/post"))?;

        let content_html = post
            .get("body_html")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .trim()
            .to_string();
        if content_html.is_empty() {
            continue;
        }

        let title = post
            .get("title")
            .and_then(Value::as_str)
            .map(str::to_string);
        let description = post
            .get("subtitle")
            .and_then(Value::as_str)
            .map(str::to_string);
        let published = post
            .get("post_date")
            .and_then(Value::as_str)
            .map(str::to_string);
        let author = post
            .get("publishedBylines")
            .and_then(Value::as_array)
            .and_then(|arr| arr.first())
            .and_then(|v| v.get("name"))
            .and_then(Value::as_str)
            .map(str::to_string);

        return Some(ExtractorResult {
            content_html,
            title,
            description,
            author,
            published,
            site: Some("Substack".to_string()),
        });
    }

    None
}

fn decode_json_parse_literal(script_text: &str) -> Option<String> {
    let re = Regex::new(r#"JSON\.parse\("((?:\\.|[^"\\])*)"\)"#).expect("valid regex");
    let caps = re.captures(script_text)?;
    let inner = caps.get(1)?.as_str();
    let quoted = format!("\"{inner}\"");
    serde_json::from_str::<String>(&quoted).ok()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_substack_preload_json_parse_literal() {
        let script = r#"window._preloads = JSON.parse("{\"feedData\":{\"initialPost\":{\"post\":{\"title\":\"My Post\",\"subtitle\":\"My Sub\",\"body_html\":\"<p>Hello world</p>\",\"post_date\":\"2026-03-29T00:00:00Z\",\"publishedBylines\":[{\"name\":\"Axel\"}]}}}}");"#;
        let decoded = decode_json_parse_literal(script).expect("expected decoded payload");
        let value: Value = serde_json::from_str(&decoded).expect("valid decoded JSON");
        assert_eq!(
            value
                .pointer("/feedData/initialPost/post/title")
                .and_then(Value::as_str),
            Some("My Post")
        );
    }
}
