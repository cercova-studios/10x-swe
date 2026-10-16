use crate::model::{Record, hash};
use serde::Serialize;

#[derive(Clone, Debug, Serialize)]
pub struct Passage {
    pub provider: String,
    pub account: String,
    pub external_id: String,
    pub field: String,
    pub start: usize,
    pub end: usize,
    pub text: String,
    pub field_sha256: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub cosine: Option<f32>,
}

pub fn record(record: &Record) -> Vec<Passage> {
    let mut out = Vec::new();
    for (field, text) in [("excerpt", &record.excerpt), ("note", &record.note)] {
        let digest = hash(text);
        let mut start = 0;
        while start < text.len() {
            let mut end = (start + 400).min(text.len());
            while !text.is_char_boundary(end) {
                end -= 1;
            }
            // Preserve exact offsets while preferring a word boundary to split tokens.
            if end < text.len()
                && let Some((offset, _)) = text[start..end]
                    .char_indices()
                    .rev()
                    .find(|(i, c)| *i >= 200 && c.is_whitespace())
            {
                end = start + offset + text[start + offset..].chars().next().unwrap().len_utf8();
            }
            if !text[start..end].trim().is_empty() {
                out.push(Passage {
                    provider: record.provider.clone(),
                    account: record.account.clone(),
                    external_id: record.external_id.clone(),
                    field: field.into(),
                    start,
                    end,
                    text: text[start..end].into(),
                    field_sha256: digest.clone(),
                    cosine: None,
                });
            }
            start = end;
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn exact_unicode_spans_cover_entire_fields() {
        let mut r = Record::new("manual", "fixture", "1", "https://example.org").unwrap();
        r.note = format!("{}\n{}", "研究 ".repeat(120), "verylongword".repeat(120));
        let passages = record(&r);
        assert_eq!(
            passages.iter().map(|p| p.text.as_str()).collect::<String>(),
            r.note
        );
        for p in passages {
            assert!(p.text.len() <= 400);
            assert_eq!(p.text, r.note[p.start..p.end]);
            assert_eq!(p.field_sha256, hash(&r.note));
        }
    }
}
