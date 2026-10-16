use crate::{model::Record, state, store::Store};
use anyhow::{Result, ensure};
use reqwest::{blocking::Client, redirect::Policy};
use serde_json::Value;
use std::{collections::BTreeMap, io::Read, path::Path, time::Duration};

fn http() -> Result<Client> {
    Ok(Client::builder()
        .redirect(Policy::none())
        .timeout(Duration::from_secs(30))
        .build()?)
}
fn page(client: &Client, url: &str, token: &str) -> Result<Value> {
    for attempt in 0..3 {
        let response = client.get(url).bearer_auth(token).send().map_err(|_| {
            anyhow::anyhow!("Provider connection failed; previous snapshot preserved")
        })?;
        if response.status().as_u16() == 429 && attempt < 2 {
            let seconds = response
                .headers()
                .get("retry-after")
                .and_then(|h| h.to_str().ok())
                .and_then(|s| s.parse::<u64>().ok())
                .unwrap_or(2)
                .clamp(1, 30);
            std::thread::sleep(Duration::from_secs(seconds));
            continue;
        }
        ensure!(
            response.status().is_success(),
            "Provider HTTP {}; previous snapshot preserved",
            response.status().as_u16()
        );
        let mut raw = Vec::new();
        response.take(8 * 1024 * 1024 + 1).read_to_end(&mut raw)?;
        ensure!(raw.len() <= 8 * 1024 * 1024, "Provider page exceeds 8 MiB");
        return serde_json::from_slice(&raw)
            .map_err(|_| anyhow::anyhow!("Invalid provider response"));
    }
    anyhow::bail!("Provider rate limit exhausted")
}
fn string(v: &Value, key: &str) -> String {
    v[key].as_str().unwrap_or("").into()
}
fn identifier(v: &Value) -> Result<String> {
    if let Some(s) = v.as_str() {
        Ok(s.into())
    } else if v.is_number() {
        Ok(v.to_string())
    } else {
        anyhow::bail!("Missing provider identity")
    }
}
pub fn normalize(provider: &str, account: &str, v: &Value) -> Result<Record> {
    let (id, url) = if provider == "raindrop" {
        (identifier(&v["_id"])?, string(v, "link"))
    } else {
        (identifier(&v["id"])?, string(v, "url"))
    };
    let mut r = Record::new(provider, account, &id, &url)?;
    r.title = string(v, "title");
    if provider == "raindrop" {
        r.excerpt = string(v, "excerpt");
        r.note = string(v, "note");
        if let Some(tags) = v["tags"].as_array() {
            r.tags = tags
                .iter()
                .map(|t| {
                    t.as_str()
                        .map(str::to_owned)
                        .ok_or_else(|| anyhow::anyhow!("Invalid Raindrop tag"))
                })
                .collect::<Result<_>>()?;
        }
        r.folder = identifier(&v["collection"]["$id"]).unwrap_or_default();
        r.saved_at = v["created"].as_str().map(str::to_owned);
        r.updated_at = v["lastUpdate"].as_str().map(str::to_owned);
        if let Some(kind) = v["type"]
            .as_str()
            .filter(|k| ["article", "video"].contains(k))
            && (r.kind == "other" || kind == "video")
        {
            r.kind = kind.into();
            r.kind_source = "provider".into();
        }
    } else {
        r.excerpt = string(v, "description");
        r.saved_at = v["time"]
            .as_i64()
            .filter(|t| *t > 0)
            .and_then(|t| chrono::DateTime::from_timestamp(t, 0))
            .map(|t| t.to_rfc3339());
        r.folder = identifier(&v["folder_id"]).unwrap_or_default();
        if let Some(tags) = v["tags"].as_array() {
            r.tags = tags.iter().map(|t| string(t, "name")).collect();
        }
        if v["category"].as_u64() == Some(2) {
            r.kind = "video".into();
            r.kind_source = "provider".into();
        }
    }
    r.validate()?;
    Ok(r)
}
pub fn snapshot(
    home: &Path,
    provider: &str,
) -> Result<(String, Vec<Record>, Option<Vec<crate::graph::Relation>>)> {
    let account = state::account(home, provider)?;
    let token = state::credential(home, provider)?;
    if provider == "neon" {
        let snapshot = Store::new(token)?.snapshot(&account)?;
        return Ok((account, snapshot.records, Some(snapshot.relations)));
    }
    ensure!(
        ["instapaper", "raindrop"].contains(&provider),
        "Unsupported reader"
    );
    let client = http()?;
    let mut records = BTreeMap::new();
    let mut offset = 0usize;
    for page_number in 0..100000 {
        let url = if provider == "raindrop" {
            format!("https://api.raindrop.io/rest/v1/raindrops/0?perpage=50&page={page_number}")
        } else {
            format!("https://www.instapaper.com/api/2/bookmarks?since=1&limit=100&offset={offset}")
        };
        let data = page(&client, &url, &token)?;
        if provider == "raindrop" {
            ensure!(data["result"] == true, "Invalid Raindrop response");
        }
        let items = data[if provider == "raindrop" {
            "items"
        } else {
            "bookmarks"
        }]
        .as_array()
        .ok_or_else(|| anyhow::anyhow!("Missing provider bookmark list"))?;
        for item in items {
            let r = normalize(provider, &account, item)?;
            records.insert(r.external_id.clone(), r);
        }
        let mut count = items.len();
        if provider == "instapaper"
            && let Some(deleted) = data["deleted_ids"].as_array()
        {
            count += deleted.len();
            for id in deleted {
                records.remove(&identifier(id)?);
            }
        }
        if count < if provider == "raindrop" { 50 } else { 100 } {
            return Ok((account, records.into_values().collect(), None));
        }
        offset += count;
    }
    anyhow::bail!("Pagination work budget exhausted")
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn raindrop_specific_kind_overrides_article() {
        let r = normalize(
            "raindrop",
            "me",
            &serde_json::json!({"_id":1,"link":"https://arxiv.org/abs/2401.123","type":"article"}),
        )
        .unwrap();
        assert_eq!(r.kind, "paper");
    }
    #[test]
    fn missing_instapaper_url_rejects_snapshot_record() {
        assert!(
            normalize(
                "instapaper",
                "me",
                &serde_json::json!({"id":1,"title":"email content"})
            )
            .is_err()
        );
    }
}
