use once_cell::sync::Lazy;
use regex::Regex;

static TAG_RE: Lazy<Regex> = Lazy::new(|| Regex::new(r"(?is)<[^>]+>").expect("valid regex"));
static WS_RE: Lazy<Regex> = Lazy::new(|| Regex::new(r"\s+").expect("valid regex"));

pub fn strip_tags(input: &str) -> String {
    let no_tags = TAG_RE.replace_all(input, " ");
    WS_RE.replace_all(no_tags.trim(), " ").to_string()
}

pub fn count_words(text: &str) -> usize {
    let mut cjk_count = 0usize;
    let mut word_count = 0usize;
    let mut in_word = false;

    for c in text.chars() {
        let code = c as u32;
        if is_cjk(code) {
            cjk_count += 1;
            in_word = false;
        } else if c.is_whitespace() {
            in_word = false;
        } else if !in_word {
            word_count += 1;
            in_word = true;
        }
    }

    cjk_count + word_count
}

pub fn text_preview(text: &str, max_chars: usize) -> String {
    text.chars().take(max_chars).collect()
}

fn is_cjk(code: u32) -> bool {
    matches!(
        code,
        0x3040..=0x309F
            | 0x30A0..=0x30FF
            | 0x3400..=0x4DBF
            | 0x4E00..=0x9FFF
            | 0xF900..=0xFAFF
            | 0xAC00..=0xD7AF
    )
}
