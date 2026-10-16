use once_cell::sync::Lazy;
use regex::Regex;

static FOOTNOTE_BACKREF_RE: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r#"(?is)<a[^>]*class=["'][^"']*footnote-backref[^"']*["'][^>]*>.*?</a>"#)
        .expect("valid regex")
});

pub fn standardize_footnotes(input: &str) -> String {
    // Keep this phase intentionally simple in v1: preserve footnote content while
    // removing noisy back-reference links that pollute markdown output.
    FOOTNOTE_BACKREF_RE.replace_all(input, "").to_string()
}
