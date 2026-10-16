use once_cell::sync::Lazy;
use scraper::Selector;

use crate::dom_ops::{detach_nodes, parse_fragment, serialize_fragment};

const MIN_DIMENSION: u32 = 33;

static MEDIA_SEL: Lazy<Selector> =
    Lazy::new(|| Selector::parse("img, svg").expect("valid selector"));

pub fn remove_small_images(input: &str) -> String {
    let mut doc = parse_fragment(input);
    let mut ids = Vec::new();

    for el in doc.select(&MEDIA_SEL) {
        let width = el
            .value()
            .attr("width")
            .and_then(|v| v.trim().parse::<u32>().ok());
        let height = el
            .value()
            .attr("height")
            .and_then(|v| v.trim().parse::<u32>().ok());
        if let (Some(w), Some(h)) = (width, height) {
            if w < MIN_DIMENSION || h < MIN_DIMENSION {
                ids.push(el.id());
            }
        }
    }

    detach_nodes(&mut doc, ids);
    serialize_fragment(&doc)
}

#[cfg(test)]
mod tests {
    use super::remove_small_images;

    #[test]
    fn removes_tiny_images_keeps_large() {
        let html =
            r#"<img width="16" height="16" src="a.png"><img width="200" height="200" src="b.png">"#;
        let cleaned = remove_small_images(html);
        assert!(!cleaned.contains("a.png"));
        assert!(cleaned.contains("b.png"));
    }
}
