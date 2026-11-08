use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::BTreeMap;

#[derive(Clone, Debug, Default, Serialize, Deserialize, PartialEq)]
pub struct Turn {
    pub line: usize,
    pub role: String,
    pub text: String,
    pub timestamp: Option<Value>,
    pub pointer: String,
    pub record_sha256: String,
    pub original_sha256: String,
    pub redacted: bool,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct Session {
    pub agent: String,
    pub native_id: String,
    pub cwd: String,
    pub title: String,
    pub summary: String,
    pub body: String,
    pub updated_at: i64,
    pub source_path: String,
    pub content_hash: String,
    pub turns: Vec<Turn>,
    pub limitations: Vec<String>,
}
impl Session {
    pub fn id(&self) -> String {
        format!("{}:{}", self.agent, self.native_id)
    }
}

#[derive(Clone, Debug, Serialize)]
pub struct Hit {
    pub agent: String,
    pub native_id: String,
    pub cwd: String,
    pub title: String,
    pub summary: String,
    pub snippet: String,
    pub updated_at: i64,
    pub source_path: String,
    pub strategy: String,
    pub rank: f64,
    pub citations: Vec<Value>,
    pub id: String,
}
#[derive(Debug, Serialize)]
pub struct SearchResult {
    pub query: String,
    pub mode: String,
    pub hits: Vec<Hit>,
    pub strategies_used: Vec<String>,
    pub strategies_skipped: BTreeMap<String, String>,
}
#[derive(Debug)]
pub struct StrategyUnavailable(pub String, pub String);
impl std::fmt::Display for StrategyUnavailable {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}: {}", self.0, self.1)
    }
}
impl std::error::Error for StrategyUnavailable {}
