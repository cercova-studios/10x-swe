use once_cell::sync::Lazy;
use regex::Regex;
use scraper::{ElementRef, Node, Selector};

use crate::dom_ops::{
    contains_technical_content, detach_nodes, next_element_sibling, parse_fragment,
    serialize_fragment,
};

static H1_SEL: Lazy<Selector> = Lazy::new(|| Selector::parse("h1").expect("valid selector"));
static DATE_RE: Lazy<Regex> = Lazy::new(|| {
    Regex::new(
        r"(?i)\b(\d{4}-\d{2}-\d{2}|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2},\s+\d{4}|\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{4})\b",
    )
    .expect("valid regex")
});

pub fn remove_metadata_block(content_html: &str, has_author_or_published: bool) -> String {
    if !has_author_or_published {
        return content_html.to_string();
    }

    let mut doc = parse_fragment(content_html);
    let Some(h1) = doc.select(&H1_SEL).next() else {
        return content_html.to_string();
    };
    let h1_id = h1.id();
    let Some(following_id) = next_element_sibling(&doc, h1_id) else {
        return content_html.to_string();
    };

    let Some(following_node) = doc.tree.get(following_id) else {
        return content_html.to_string();
    };
    let Node::Element(el) = following_node.value() else {
        return content_html.to_string();
    };
    if !matches!(el.name(), "div" | "p" | "section") {
        return content_html.to_string();
    }

    let Some(following) = ElementRef::wrap(following_node) else {
        return content_html.to_string();
    };
    if contains_technical_content(&following) {
        return content_html.to_string();
    }
    let following_text = following
        .text()
        .collect::<String>()
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ");
    if following_text.is_empty() || following_text.len() > 300 {
        return content_html.to_string();
    }
    if !DATE_RE.is_match(&following_text) {
        return content_html.to_string();
    }

    detach_nodes(&mut doc, [following_id]);
    serialize_fragment(&doc)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn removes_h1_adjacent_date_block_when_metadata_present() {
        let html = "<h1>Title</h1><div>By Alice • Mar 29, 2026</div><p>Body</p>";
        let cleaned = remove_metadata_block(html, true);
        assert_eq!(cleaned, "<h1>Title</h1><p>Body</p>");
    }

    #[test]
    fn keeps_following_block_when_no_date() {
        let html = "<h1>Title</h1><div>Important intro block</div><p>Body</p>";
        let cleaned = remove_metadata_block(html, true);
        assert_eq!(cleaned, html);
    }
}
