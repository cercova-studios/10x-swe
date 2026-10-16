use once_cell::sync::Lazy;
use regex::Regex;

static GITHUB_ALERT_RE: Lazy<Regex> = Lazy::new(|| {
    Regex::new(
        r#"(?is)<blockquote[^>]*>\s*<p>\s*<strong>\s*(note|tip|important|warning|caution)\s*</strong>\s*(.*?)</p>\s*</blockquote>"#,
    )
    .expect("valid regex")
});

pub fn standardize_callouts(input: &str) -> String {
    GITHUB_ALERT_RE
        .replace_all(input, |caps: &regex::Captures<'_>| {
            let kind = caps
                .get(1)
                .map(|m| m.as_str())
                .unwrap_or("note")
                .to_lowercase();
            let body = caps.get(2).map(|m| m.as_str()).unwrap_or_default().trim();
            format!(r#"<div class="callout" data-callout="{kind}"><p>{body}</p></div>"#)
        })
        .to_string()
}
