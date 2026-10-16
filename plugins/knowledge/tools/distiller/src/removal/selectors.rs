use once_cell::sync::Lazy;
use scraper::Selector;

use crate::constants::PARTIAL_PATTERNS;
use crate::dom_ops::{
    attr_match_blob, contains_technical_content, detach_nodes, parse_fragment, serialize_fragment,
    sort_shallow_first,
};

static SCRIPT_SEL: Lazy<Selector> =
    Lazy::new(|| Selector::parse("script").expect("valid selector"));
static STYLE_SEL: Lazy<Selector> = Lazy::new(|| Selector::parse("style").expect("valid selector"));
static NOSCRIPT_SEL: Lazy<Selector> =
    Lazy::new(|| Selector::parse("noscript").expect("valid selector"));
static CHROME_SEL: Lazy<Selector> =
    Lazy::new(|| Selector::parse("nav, aside, footer, header").expect("valid selector"));
static PARTIAL_BLOCK_SEL: Lazy<Selector> = Lazy::new(|| {
    Selector::parse("div, section, aside, nav, footer, header").expect("valid selector")
});

pub fn remove_by_selectors(input: &str, remove_exact: bool, remove_partial: bool) -> String {
    if !remove_exact && !remove_partial {
        return input.to_string();
    }

    let mut doc = parse_fragment(input);
    let mut ids = Vec::new();

    if remove_exact {
        for el in doc.select(&SCRIPT_SEL) {
            let typ = el.value().attr("type").unwrap_or("");
            if typ.starts_with("math/") {
                continue;
            }
            ids.push(el.id());
        }
        for el in doc.select(&STYLE_SEL) {
            ids.push(el.id());
        }
        for el in doc.select(&NOSCRIPT_SEL) {
            ids.push(el.id());
        }
        for el in doc.select(&CHROME_SEL) {
            ids.push(el.id());
        }
    }

    if remove_partial {
        for el in doc.select(&PARTIAL_BLOCK_SEL) {
            if contains_technical_content(&el) {
                continue;
            }
            let blob = attr_match_blob(&el);
            if PARTIAL_PATTERNS
                .iter()
                .any(|pattern| blob.contains(pattern))
            {
                ids.push(el.id());
            }
        }
    }

    sort_shallow_first(&doc, &mut ids);
    detach_nodes(&mut doc, ids);
    serialize_fragment(&doc)
}

#[cfg(test)]
mod tests {
    use super::remove_by_selectors;

    #[test]
    fn partial_selector_cleanup_keeps_byline_blocks() {
        let html = r#"
        <article>
          <h1>Title</h1>
          <div class="byline">Alice Example</div>
          <p>Body paragraph with enough words to represent real article content.</p>
        </article>
        "#;

        let cleaned = remove_by_selectors(html, false, true);
        assert!(cleaned.contains("Alice Example"));
        assert!(cleaned.contains("Body paragraph"));
    }

    #[test]
    fn exact_selector_removes_nav_and_scripts() {
        let html = r#"
        <article>
          <nav>Menu</nav>
          <script>alert(1)</script>
          <script type="math/tex">x</script>
          <p>Body</p>
        </article>
        "#;
        let cleaned = remove_by_selectors(html, true, false);
        assert!(!cleaned.to_lowercase().contains("<nav"));
        assert!(!cleaned.contains("alert(1)"));
        assert!(cleaned.contains("math/tex") || cleaned.contains(">x<"));
        assert!(cleaned.contains("Body"));
    }
}
