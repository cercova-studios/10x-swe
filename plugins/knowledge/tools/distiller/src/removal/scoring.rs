use once_cell::sync::Lazy;
use scraper::Selector;

use crate::dom::count_words;
use crate::dom_ops::{
    contains_technical_content, detach_nodes, parse_fragment, serialize_fragment,
    sort_shallow_first,
};
use crate::scoring::{is_likely_content, score_non_content_block};

static BLOCK_SEL: Lazy<Selector> = Lazy::new(|| {
    Selector::parse("div, section, aside, nav, footer, header").expect("valid selector")
});

pub fn remove_low_scoring_blocks(input: &str) -> String {
    let mut doc = parse_fragment(input);
    let mut ids = Vec::new();

    for el in doc.select(&BLOCK_SEL) {
        if contains_technical_content(&el) || is_likely_content(&el) {
            continue;
        }
        let text = el.text().collect::<String>();
        if count_words(&text) < 8 {
            continue;
        }
        let score = score_non_content_block(&el);
        if score < 0.0 {
            ids.push(el.id());
        }
    }

    sort_shallow_first(&doc, &mut ids);
    detach_nodes(&mut doc, ids);
    serialize_fragment(&doc)
}
