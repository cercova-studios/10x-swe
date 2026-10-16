use once_cell::sync::Lazy;
use scraper::{Node, Selector};
use url::Url;

use crate::dom_ops::{parse_fragment, serialize_fragment};

static ELEMENTS: Lazy<Selector> = Lazy::new(|| Selector::parse("*").expect("valid selector"));

pub fn sanitize_html(input: &str) -> String {
    let mut doc = parse_fragment(input);
    let ids: Vec<_> = doc.select(&ELEMENTS).map(|el| el.id()).collect();
    for id in ids {
        let Some(mut node) = doc.tree.get_mut(id) else {
            continue;
        };
        let Node::Element(el) = node.value() else {
            continue;
        };
        if matches!(
            el.name(),
            "script"
                | "style"
                | "noscript"
                | "frame"
                | "frameset"
                | "iframe"
                | "object"
                | "embed"
                | "applet"
                | "base"
        ) {
            node.detach();
            continue;
        }
        // DOM attributes are entity-decoded; source code text is never rewritten.
        el.attrs.retain(|(name, value)| {
            let name = name.local.as_ref();
            !name.starts_with("on")
                && name != "srcdoc"
                && !(is_url_attribute(name) && is_dangerous_url(value))
        });
    }
    serialize_fragment(&doc)
}

pub fn resolve_relative_urls(input: &str, base_url: &str) -> String {
    let Ok(base) = Url::parse(base_url) else {
        return input.to_string();
    };
    let mut doc = parse_fragment(input);
    let ids: Vec<_> = doc.select(&ELEMENTS).map(|el| el.id()).collect();
    for id in ids {
        let Some(mut node) = doc.tree.get_mut(id) else {
            continue;
        };
        let Node::Element(el) = node.value() else {
            continue;
        };
        for (name, value) in &mut el.attrs {
            if is_url_attribute(name.local.as_ref()) {
                if let Some(resolved) = resolve_url(&base, value) {
                    *value = resolved.as_str().into();
                }
            }
        }
    }
    serialize_fragment(&doc)
}

fn is_url_attribute(name: &str) -> bool {
    matches!(name, "href" | "src" | "action" | "formaction")
}

fn resolve_url(base: &Url, relative: &str) -> Option<String> {
    let trimmed = relative.trim();
    if trimmed.is_empty() || trimmed.starts_with('#') || trimmed.starts_with("data:") {
        return Some(trimmed.to_string());
    }
    base.join(trimmed).ok().map(|u| u.to_string())
}

pub fn is_dangerous_url(url: &str) -> bool {
    let normalized: String = url
        .chars()
        .filter(|c| !c.is_whitespace() && !c.is_control())
        .collect();
    let lower = normalized.to_lowercase();
    lower.starts_with("javascript:") || lower.starts_with("data:text/html")
}

#[cfg(test)]
mod tests {
    use super::sanitize_html;

    #[test]
    fn strips_void_base_elements() {
        let sanitized = sanitize_html(r#"<head><base href="https://evil.test/"></head>"#);
        assert!(!sanitized.contains("<base"));
    }
}
