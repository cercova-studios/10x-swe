use once_cell::sync::Lazy;
use scraper::Selector;

use crate::dom_ops::{detach_nodes, parse_fragment, serialize_fragment, sort_shallow_first};

static CANDIDATE_SEL: Lazy<Selector> = Lazy::new(|| {
    Selector::parse("div, section, aside, nav, footer, header, span").expect("valid selector")
});

pub fn remove_hidden_elements(input: &str) -> String {
    let mut doc = parse_fragment(input);
    let mut ids = Vec::new();

    for el in doc.select(&CANDIDATE_SEL) {
        if is_hidden(&el) {
            ids.push(el.id());
        }
    }

    sort_shallow_first(&doc, &mut ids);
    detach_nodes(&mut doc, ids);
    serialize_fragment(&doc)
}

fn is_hidden(el: &scraper::ElementRef<'_>) -> bool {
    if let Some(style) = el.value().attr("style") {
        let style = style.to_ascii_lowercase().replace(' ', "");
        if style.contains("display:none")
            || style.contains("visibility:hidden")
            || style.contains("opacity:0")
        {
            return true;
        }
    }

    if let Some(class) = el.value().attr("class") {
        let class = format!(" {class} ").to_ascii_lowercase();
        if class.contains(" hidden ") || class.contains(" invisible ") {
            return true;
        }
    }

    false
}

#[cfg(test)]
mod tests {
    use super::remove_hidden_elements;

    #[test]
    fn removes_display_none_blocks() {
        let html = r#"<div style="display:none">secret</div><p>visible</p>"#;
        let cleaned = remove_hidden_elements(html);
        assert!(!cleaned.contains("secret"));
        assert!(cleaned.contains("visible"));
    }
}
