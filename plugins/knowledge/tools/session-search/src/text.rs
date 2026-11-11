use chrono::{DateTime, NaiveDate, NaiveDateTime, Utc};
use regex::Regex;
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::{path::Path, sync::LazyLock};

pub fn sha(bytes: impl AsRef<[u8]>) -> String {
    format!("{:x}", Sha256::digest(bytes.as_ref()))
}
pub fn content_hash(parts: &[&str]) -> String {
    let mut h = Sha256::new();
    for part in parts {
        h.update(part.as_bytes());
        h.update([0]);
    }
    format!("{:x}", h.finalize())[..16].into()
}
static SECRET: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r#"(?i)(sk-[A-Za-z0-9]{10,}|ghp_[A-Za-z0-9]{20,}|xai-[A-Za-z0-9]{10,}|Bearer\s+[A-Za-z0-9._\-]{12,}|api[_-]?key["'\s:=]+[A-Za-z0-9._\-]{12,})"#).unwrap()
});
pub fn redact(text: &str) -> String {
    SECRET.replace_all(text, "[redacted]").into_owned()
}
pub fn squeeze(text: &str) -> String {
    text.replace('\0', " ")
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
}
pub fn clip(text: &str, n: usize) -> String {
    let s = squeeze(text);
    if s.chars().count() <= n {
        s
    } else {
        format!(
            "{}…",
            s.chars()
                .take(n.saturating_sub(1))
                .collect::<String>()
                .trim_end()
        )
    }
}
pub fn title(parts: &[String]) -> String {
    parts
        .iter()
        .map(|s| clip(&redact(s), 180))
        .find(|s| !s.is_empty())
        .unwrap_or_else(|| "(untitled)".into())
}
pub fn body(parts: &[String]) -> String {
    clip(
        &parts
            .iter()
            .filter(|p| !p.is_empty())
            .map(|p| redact(p))
            .collect::<Vec<_>>()
            .join("\n"),
        32000,
    )
}
pub fn snippet(text: &str, query: &str, n: usize) -> String {
    let text = squeeze(&redact(text));
    let needle = query.split_whitespace().next().unwrap_or("").to_lowercase();
    let lower = text.to_lowercase();
    let start = if needle.is_empty() {
        0
    } else {
        lower
            .find(&needle)
            .map(|b| lower[..b].chars().count().saturating_sub(40))
            .unwrap_or(0)
    };
    clip(&text.chars().skip(start).collect::<String>(), n)
}
pub fn string(v: &Value) -> String {
    match v {
        Value::String(s) => s.clone(),
        Value::Null => String::new(),
        _ => v.to_string(),
    }
}
pub fn first<'a>(v: &'a Value, keys: &[&str]) -> &'a Value {
    keys.iter()
        .map(|k| &v[*k])
        .find(|v| match v {
            Value::Null => false,
            Value::Bool(b) => *b,
            Value::String(s) => !s.is_empty(),
            Value::Number(n) => n.as_f64() != Some(0.0),
            Value::Array(a) => !a.is_empty(),
            Value::Object(m) => !m.is_empty(),
        })
        .unwrap_or(&Value::Null)
}
pub fn flatten(v: &Value, depth: usize) -> String {
    if depth > 6 {
        return String::new();
    }
    match v {
        Value::Null => String::new(),
        Value::String(s) => s.clone(),
        Value::Bool(b) => if *b { "True" } else { "False" }.into(),
        Value::Number(n) => n.to_string(),
        Value::Array(a) => a
            .iter()
            .map(|v| flatten(v, depth + 1))
            .filter(|s| !s.is_empty())
            .collect::<Vec<_>>()
            .join("\n"),
        Value::Object(m) => {
            if let Some(s) = m.get("text").and_then(Value::as_str) {
                return s.into();
            }
            if let Some(v) = m.get("content") {
                return flatten(v, depth + 1);
            }
            ["message", "display", "summary", "title", "claim"]
                .iter()
                .filter_map(|k| m.get(*k))
                .map(|v| flatten(v, depth + 1))
                .filter(|s| !s.is_empty())
                .collect::<Vec<_>>()
                .join("\n")
        }
    }
}
pub fn time(v: &Value) -> i64 {
    if let Some(n) = v.as_f64() {
        return if n > 1e14 {
            n / 1000.0
        } else if n > 1e12 {
            n
        } else if n > 1e9 {
            n * 1000.0
        } else {
            n
        } as i64;
    }
    let Some(s) = v.as_str() else { return 0 };
    let s = s.trim();
    if let Ok(n) = s.parse::<u64>() {
        return time(&Value::from(n));
    }
    if let Ok(dt) = DateTime::parse_from_rfc3339(&s.replace(' ', "T")) {
        return dt.timestamp_millis();
    }
    for format in ["%Y-%m-%dT%H:%M:%S%.f", "%Y-%m-%d %H:%M:%S%.f"] {
        if let Ok(dt) = NaiveDateTime::parse_from_str(s, format) {
            return dt.and_utc().timestamp_millis();
        }
    }
    NaiveDate::parse_from_str(s, "%Y-%m-%d")
        .ok()
        .and_then(|d| d.and_hms_opt(0, 0, 0))
        .map(|d| d.and_utc().timestamp_millis())
        .unwrap_or(0)
}
pub fn since(s: Option<&str>) -> Option<i64> {
    let s = s?.trim().to_lowercase();
    for (suffix, unit) in [('d', 86_400_000), ('h', 3_600_000)] {
        if let Some(n) = s
            .strip_suffix(suffix)
            .and_then(|v| v.parse::<i64>().ok())
            .filter(|v| *v >= 0)
        {
            return n
                .checked_mul(unit)
                .and_then(|delta| Utc::now().timestamp_millis().checked_sub(delta));
        }
    }
    let t = time(&Value::String(s));
    (t != 0).then_some(t)
}
pub fn mtime(path: &Path) -> i64 {
    path.metadata()
        .ok()
        .and_then(|m| m.modified().ok())
        .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
        .map(|d| d.as_millis() as i64)
        .unwrap_or(0)
}
pub fn decode(s: &str) -> String {
    percent_decode(s)
}
pub fn percent_decode(s: &str) -> String {
    let mut out = Vec::new();
    let b = s.as_bytes();
    let mut i = 0;
    while i < b.len() {
        if b[i] == b'%'
            && i + 2 < b.len()
            && let (Some(a), Some(c)) = (
                (b[i + 1] as char).to_digit(16),
                (b[i + 2] as char).to_digit(16),
            )
        {
            out.push((a * 16 + c) as u8);
            i += 3;
            continue;
        }
        out.push(b[i]);
        i += 1
    }
    String::from_utf8_lossy(&out).into_owned()
}
// Python's sorted-key, UTF-8 JSON with default separators defines existing session revisions.
pub fn revision_json(v: &Value) -> String {
    match v {
        Value::Array(a) => format!(
            "[{}]",
            a.iter().map(revision_json).collect::<Vec<_>>().join(", ")
        ),
        Value::Object(m) => {
            let mut keys = m.keys().collect::<Vec<_>>();
            keys.sort();
            format!(
                "{{{}}}",
                keys.into_iter()
                    .map(|k| format!(
                        "{}: {}",
                        serde_json::to_string(k).unwrap(),
                        revision_json(&m[k])
                    ))
                    .collect::<Vec<_>>()
                    .join(", ")
            )
        }
        _ => v.to_string(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    #[test]
    fn revision_encoding_preserves_existing_hash_contract() {
        assert_eq!(
            revision_json(&json!({"z": ["日本語", true], "a": 1})),
            r#"{"a": 1, "z": ["日本語", true]}"#
        );
        assert_eq!(
            sha("abc"),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        );
    }
    #[test]
    fn untrusted_dates_and_percent_escapes_do_not_panic() {
        assert_eq!(since(Some("9223372036854775807d")), None);
        assert_eq!(decode("%E6%97%A5%日本語"), "日%日本語");
        assert_eq!(time(&json!("2026-10-12T12:00:00Z")), 1791806400000);
    }
}
