use once_cell::sync::Lazy;
use regex::Regex;
use scraper::{Html, Selector};
use serde_json::Value;

use crate::dom::strip_tags;
use crate::types::MetaTag;

static DATE_RE: Lazy<Regex> = Lazy::new(|| {
    Regex::new(
        r"(?i)\b(\d{4}-\d{2}-\d{2}|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2},\s+\d{4}|\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{4})\b",
    )
    .expect("valid regex")
});

pub fn collect_meta_tags(html: &Html) -> Vec<MetaTag> {
    let selector = Selector::parse("meta").expect("valid selector");
    html.select(&selector)
        .map(|el| MetaTag {
            name: el.value().attr("name").map(str::to_string),
            property: el.value().attr("property").map(str::to_string),
            content: el.value().attr("content").map(str::to_string),
        })
        .collect()
}

pub fn extract_schema_org(html: &Html) -> Option<Value> {
    let selector = Selector::parse("script[type=\"application/ld+json\"]").expect("valid selector");
    for script in html.select(&selector) {
        let text = script.text().collect::<String>();
        if let Ok(parsed) = serde_json::from_str::<Value>(&text) {
            return Some(parsed);
        }
    }
    None
}

pub fn schema_text(schema: Option<&Value>) -> Option<String> {
    fn walk(v: &Value) -> Option<String> {
        if let Some(s) = v.get("text").and_then(Value::as_str) {
            return Some(s.to_string());
        }
        if let Some(s) = v.get("articleBody").and_then(Value::as_str) {
            return Some(s.to_string());
        }
        match v {
            Value::Array(arr) => arr.iter().find_map(walk),
            Value::Object(map) => map.values().find_map(walk),
            _ => None,
        }
    }
    schema.and_then(walk)
}

pub fn extract_title(html: &Html, schema: Option<&Value>, markdown_hint: Option<&str>) -> String {
    if let Some(s) = schema_get_string(schema, &["headline", "name"]) {
        return clean_title(&s);
    }
    if let Some(s) = meta_by_keys(
        html,
        &[
            "og:title",
            "twitter:title",
            "sailthru.title",
            "dc.title",
            "title",
        ],
    ) {
        return clean_title(&s);
    }
    if let Some(title) = title_tag(html) {
        return clean_title(&title);
    }
    markdown_hint.unwrap_or_default().trim().to_string()
}

pub fn extract_description(html: &Html, schema: Option<&Value>, markdown: Option<&str>) -> String {
    if let Some(s) = schema_get_string(schema, &["description"]) {
        return s.trim().to_string();
    }
    if let Some(s) = meta_by_keys(
        html,
        &["description", "og:description", "twitter:description"],
    ) {
        return s.trim().to_string();
    }
    markdown
        .map(|m| m.lines().skip(1).take(3).collect::<Vec<_>>().join(" "))
        .unwrap_or_default()
        .trim()
        .to_string()
}

pub fn extract_author(html: &Html, schema: Option<&Value>, markdown: Option<&str>) -> String {
    if let Some(s) = schema_get_author(schema) {
        return s;
    }
    if let Some(s) = meta_by_keys(html, &["author", "article:author", "parsely-author"]) {
        return s;
    }
    markdown
        .and_then(find_byline)
        .unwrap_or_default()
        .trim()
        .to_string()
}

pub fn extract_published(html: &Html, schema: Option<&Value>, markdown: Option<&str>) -> String {
    if let Some(s) = schema_get_string(schema, &["datePublished", "dateCreated", "dateModified"]) {
        return s;
    }
    if let Some(s) = meta_by_keys(
        html,
        &[
            "article:published_time",
            "og:published_time",
            "published_time",
            "date",
        ],
    ) {
        return s;
    }
    if let Some(time) = extract_time_tag(html) {
        return time;
    }
    markdown
        .and_then(|m| DATE_RE.find(m).map(|x| x.as_str().to_string()))
        .unwrap_or_default()
}

pub fn extract_site(html: &Html, schema: Option<&Value>, url: Option<&str>) -> String {
    if let Some(s) = schema_get_string(
        schema,
        &["publisher.name", "isPartOf.name", "sourceOrganization.name"],
    ) {
        return s;
    }
    if let Some(s) = meta_by_keys(html, &["og:site_name", "application-name"]) {
        return s;
    }
    extract_domain(url)
}

pub fn extract_image(html: &Html, schema: Option<&Value>) -> String {
    if let Some(s) = schema_get_string(schema, &["image.url", "image", "thumbnailUrl"]) {
        return s;
    }
    meta_by_keys(html, &["og:image", "twitter:image"]).unwrap_or_default()
}

pub fn extract_favicon(html: &Html, url: Option<&str>) -> String {
    let selector = Selector::parse("link[rel~=\"icon\" i], link[rel=\"shortcut icon\" i]")
        .expect("valid selector");
    if let Some(link) = html.select(&selector).next() {
        return link.value().attr("href").unwrap_or_default().to_string();
    }
    let domain = extract_domain(url);
    if domain.is_empty() {
        String::new()
    } else {
        format!("https://{domain}/favicon.ico")
    }
}

pub fn extract_language(html: &Html) -> String {
    let html_sel = Selector::parse("html[lang]").expect("valid selector");
    html.select(&html_sel)
        .next()
        .and_then(|el| el.value().attr("lang"))
        .unwrap_or_default()
        .to_string()
}

pub fn extract_domain(url: Option<&str>) -> String {
    url.and_then(|u| url::Url::parse(u).ok())
        .and_then(|u| u.domain().map(str::to_string))
        .unwrap_or_default()
}

fn meta_by_keys(html: &Html, keys: &[&str]) -> Option<String> {
    let selector = Selector::parse("meta").expect("valid selector");
    for meta in html.select(&selector) {
        let name = meta.value().attr("name").unwrap_or_default();
        let property = meta.value().attr("property").unwrap_or_default();
        let key = if property.is_empty() { name } else { property };
        if keys.iter().any(|k| key.eq_ignore_ascii_case(k)) {
            if let Some(content) = meta.value().attr("content") {
                let clean = strip_tags(content).trim().to_string();
                if !clean.is_empty() {
                    return Some(clean);
                }
            }
        }
    }
    None
}

fn title_tag(html: &Html) -> Option<String> {
    let selector = Selector::parse("title").expect("valid selector");
    html.select(&selector)
        .next()
        .map(|t| t.text().collect::<String>())
        .map(|s| strip_tags(&s))
        .map(|s| s.trim().to_string())
}

fn clean_title(input: &str) -> String {
    let mut title = strip_tags(input).trim().to_string();
    for sep in [" | ", " - ", " — ", " – ", " · ", " / "] {
        if let Some((left, right)) = title.split_once(sep) {
            if left.split_whitespace().count() >= right.split_whitespace().count() {
                title = left.to_string();
            } else {
                title = right.to_string();
            }
        }
    }
    title.trim().to_string()
}

fn schema_get_string(schema: Option<&Value>, paths: &[&str]) -> Option<String> {
    for path in paths {
        if let Some(v) = schema.and_then(|s| schema_get_path(s, path)) {
            return Some(v);
        }
    }
    None
}

fn schema_get_author(schema: Option<&Value>) -> Option<String> {
    if let Some(v) = schema_get_string(schema, &["author.name", "creator.name"]) {
        return Some(v);
    }
    if let Some(name) = schema
        .and_then(|s| schema_get_path_value(s, "author"))
        .and_then(Value::as_str)
    {
        return Some(name.to_string());
    }
    None
}

fn schema_get_path(value: &Value, path: &str) -> Option<String> {
    schema_get_path_value(value, path).and_then(|v| match v {
        Value::String(s) => Some(s.to_string()),
        Value::Number(n) => Some(n.to_string()),
        _ => None,
    })
}

fn schema_get_path_value<'a>(value: &'a Value, path: &str) -> Option<&'a Value> {
    let mut current = value;
    for part in path.split('.') {
        match current {
            Value::Object(map) => current = map.get(part)?,
            Value::Array(arr) => {
                current = arr.iter().find_map(|v| schema_get_path_value(v, part))?;
            }
            _ => return None,
        }
    }
    Some(current)
}

fn extract_time_tag(html: &Html) -> Option<String> {
    let selector = Selector::parse("time[datetime], time").expect("valid selector");
    html.select(&selector).next().map(|t| {
        t.value()
            .attr("datetime")
            .map(str::to_string)
            .unwrap_or_else(|| strip_tags(&t.text().collect::<String>()))
    })
}

fn find_byline(markdown: &str) -> Option<String> {
    for line in markdown.lines().take(20) {
        let trimmed = line.trim();
        if trimmed.to_lowercase().starts_with("by ") && trimmed.len() < 80 {
            return Some(
                trimmed
                    .trim_start_matches("By ")
                    .trim_start_matches("by ")
                    .to_string(),
            );
        }
    }
    None
}
