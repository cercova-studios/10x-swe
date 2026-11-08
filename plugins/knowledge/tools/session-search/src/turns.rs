use crate::{
    model::{Session, Turn},
    text::*,
};
use anyhow::{Result, bail};
use serde_json::{Value, json};
use std::{
    fs::File,
    io::{BufRead, BufReader, Read},
    path::Path,
};
const LINE: u64 = 16 * 1024 * 1024;

pub struct Lines {
    reader: BufReader<File>,
    strict: bool,
    line: usize,
    finished: bool,
    pub limitations: Vec<String>,
}
pub fn lines(path: &Path, strict: bool) -> Result<Lines> {
    Ok(Lines {
        reader: BufReader::new(File::open(path)?),
        strict,
        line: 0,
        finished: false,
        limitations: Vec::new(),
    })
}
impl Lines {
    fn read_next(&mut self) -> Result<Option<(usize, String, Value)>> {
        loop {
            let mut raw = Vec::new();
            self.reader
                .by_ref()
                .take(LINE + 1)
                .read_until(b'\n', &mut raw)?;
            if raw.is_empty() {
                return Ok(None);
            }
            self.line += 1;
            let line = self.line;
            if raw.len() as u64 > LINE {
                while !raw.ends_with(b"\n") {
                    raw.clear();
                    self.reader
                        .by_ref()
                        .take(LINE + 1)
                        .read_until(b'\n', &mut raw)?;
                    if raw.is_empty() {
                        break;
                    }
                }
                self.limitations
                    .push(format!("JSONL line {line} omitted: record exceeds 16 MiB"));
                continue;
            }
            let raw = if self.strict {
                String::from_utf8(raw)?
            } else {
                String::from_utf8_lossy(&raw).into_owned()
            };
            if raw.trim().is_empty() {
                continue;
            }
            match serde_json::from_str::<Value>(&raw) {
                Ok(v) if v.is_object() => return Ok(Some((line, raw, v))),
                Ok(_) => {}
                Err(_) if self.strict && !raw.ends_with('\n') => return Ok(None),
                Err(_) if self.strict => bail!("Malformed session record at line {line}"),
                Err(_) => {}
            }
        }
    }
}
impl Iterator for Lines {
    type Item = Result<(usize, String, Value)>;
    fn next(&mut self) -> Option<Self::Item> {
        if self.finished {
            return None;
        }
        match self.read_next() {
            Ok(Some(v)) => Some(Ok(v)),
            Ok(None) => {
                self.finished = true;
                None
            }
            Err(e) => {
                self.finished = true;
                Some(Err(e))
            }
        }
    }
}
fn content(v: &Value) -> String {
    match v {
        Value::String(s) => s.clone(),
        Value::Array(a) => a
            .iter()
            .map(content)
            .filter(|s| !s.is_empty())
            .collect::<Vec<_>>()
            .join("\n"),
        Value::Object(m) => {
            if matches!(
                m.get("type").and_then(Value::as_str),
                Some("reasoning" | "thinking" | "redacted_thinking")
            ) {
                String::new()
            } else {
                content(
                    m.get("content")
                        .or_else(|| m.get("text"))
                        .unwrap_or(&Value::Null),
                )
            }
        }
        _ => String::new(),
    }
}
pub fn read(path: &Path, agent: &str, limitations: &mut Vec<String>) -> Result<Vec<Turn>> {
    let mut responses = Vec::new();
    let mut events = Vec::new();
    let mut rows = lines(path, true)?;
    while let Some(row) = rows.next() {
        limitations.append(&mut rows.limitations);
        let (line, raw, obj) = row?;
        let (mut role, mut text, mut pointer, mut event) =
            (String::new(), String::new(), "", false);
        if agent == "codex" {
            let p = &obj["payload"];
            if !p.is_object() {
                continue;
            }
            match (obj["type"].as_str(), p["type"].as_str()) {
                (Some("response_item"), Some("message")) => {
                    if !p["channel"].is_null()
                        && !matches!(p["channel"].as_str(), Some("final" | "commentary"))
                    {
                        continue;
                    }
                    role = string(&p["role"]);
                    text = content(&p["content"]);
                    pointer = "$.payload.content";
                }
                (
                    Some("response_item"),
                    Some("function_call_output" | "custom_tool_call_output"),
                ) => {
                    role = "tool".into();
                    text = content(&p["output"]);
                    pointer = "$.payload.output";
                }
                (Some("event_msg"), Some("user_message" | "agent_message")) => {
                    role = if p["type"] == "user_message" {
                        "user"
                    } else {
                        "assistant"
                    }
                    .into();
                    text = content(&p["message"]);
                    pointer = "$.payload.message";
                    event = true;
                }
                _ => {}
            }
        } else {
            let m = &obj["message"];
            if m.is_object() {
                role = string(if m.get("role").is_some() {
                    &m["role"]
                } else {
                    &obj["type"]
                });
                if role == "user"
                    && m["content"].as_array().is_some_and(|a| {
                        !a.is_empty() && a.iter().all(|v| v["type"] == "tool_result")
                    })
                {
                    role = "tool".into()
                }
                text = content(&m["content"]);
                pointer = "$.message.content";
            }
            if text.is_empty() && matches!(obj["type"].as_str(), Some("user" | "assistant")) {
                role = string(&obj["type"]);
                text = content(&obj["content"]);
                pointer = "$.content"
            }
        }
        if !matches!(role.as_str(), "user" | "assistant" | "tool") || text.trim().is_empty() {
            continue;
        }
        if text.len() > 4 * 1024 * 1024 {
            limitations.push(format!(
                "JSONL line {line} omitted: public turn exceeds 4 MiB"
            ));
            continue;
        }
        let clean = redact(&text);
        let turn = Turn {
            line,
            role,
            text: clean.clone(),
            timestamp: obj.get("timestamp").filter(|v| !v.is_null()).cloned(),
            pointer: pointer.into(),
            record_sha256: sha(raw.trim_end_matches(['\r', '\n'])),
            original_sha256: sha(&text),
            redacted: clean != text,
        };
        if event {
            events.push(turn)
        } else {
            responses.push(turn)
        }
    }
    limitations.append(&mut rows.limitations);
    Ok(if responses.is_empty() {
        events
    } else {
        responses
    })
}
pub fn excerpts(rec: &Session, query: &str, role: Option<&str>) -> Vec<Value> {
    let tokens = query
        .split_whitespace()
        .map(str::to_lowercase)
        .collect::<Vec<_>>();
    let mut scored = rec
        .turns
        .iter()
        .filter(|t| role.is_none_or(|r| r == t.role))
        .filter_map(|t| {
            let lower = t.text.to_lowercase();
            let score = tokens
                .iter()
                .map(|token| lower.matches(token.as_str()).count())
                .sum::<usize>();
            (score > 0).then_some((score, t))
        })
        .collect::<Vec<_>>();
    scored.sort_by_key(|(n, t)| (std::cmp::Reverse(*n), t.line));
    scored.into_iter().take(3).map(|(_,t)|{
        let lower=t.text.to_lowercase();let start=tokens.iter().filter_map(|token|lower.find(token).map(|b|lower[..b].chars().count())).min().unwrap_or(0).saturating_sub(100);
        let end=t.text.chars().count().min(start+2000);let quote=t.text.chars().skip(start).take(end-start).collect::<String>();
        json!({"agent":rec.agent,"session_id":rec.native_id,"source_path":rec.source_path,"jsonl_line":t.line,"json_pointer":t.pointer,"role":t.role,"timestamp":t.timestamp,
            "record_sha256":t.record_sha256,"original_text_sha256":t.original_sha256,"indexed_text_sha256":sha(&t.text),"excerpt_sha256":sha(&quote),
            "char_start":start,"char_end":end,"redacted":t.redacted,"quote":quote,
            "coverage":format!("Selected public-text excerpt; omitted context and hidden reasoning are not reviewed.{}",role.map(|r|format!(" Export filtered to {r} turns.")).unwrap_or_default())})
    }).collect()
}
