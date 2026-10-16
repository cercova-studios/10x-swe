use crate::{
    embedding::{self, Embedder},
    model::{Record, hash},
    state,
};
use anyhow::{Result, ensure};
use rusqlite::{Connection, params};
use serde::Serialize;
use std::collections::{BTreeMap, BTreeSet};

#[derive(Clone, Debug, Serialize)]
pub struct Book {
    pub id: String,
    pub url: String,
    pub title: String,
    pub kind: String,
    pub kind_source: String,
    pub origins: Vec<Record>,
}
impl Book {
    pub fn body(&self) -> String {
        self.origins
            .iter()
            .map(Record::body)
            .collect::<Vec<_>>()
            .join(" ")
            .chars()
            .take(12000)
            .collect()
    }
    pub fn sources(&self) -> BTreeSet<String> {
        self.origins.iter().map(|r| r.provider.clone()).collect()
    }
}
pub fn merge(
    records: Vec<Record>,
    sources: &[String],
    kinds: &[String],
    domain: Option<&str>,
) -> Vec<Book> {
    let mut groups: BTreeMap<String, Vec<Record>> = BTreeMap::new();
    for r in records {
        if !sources.is_empty() && !sources.contains(&r.provider) {
            continue;
        }
        if let Some(domain) = domain
            && url::Url::parse(&r.url)
                .ok()
                .and_then(|u| u.host_str().map(str::to_owned))
                .is_none_or(|h| h != domain && !h.ends_with(&format!(".{domain}")))
        {
            continue;
        }
        groups.entry(r.url.clone()).or_default().push(r);
    }
    groups
        .into_iter()
        .filter_map(|(url, mut origins)| {
            origins.sort_by_key(|r| {
                (
                    r.provider != "manual"
                        && r.imported_origin
                            .as_ref()
                            .is_none_or(|o| o.provider != "manual"),
                    r.origin(),
                )
            });
            let title = origins
                .iter()
                .find(|r| !r.title.is_empty())
                .map(|r| r.title.clone())
                .unwrap_or_else(|| url.clone());
            let priority = |r: &Record| match r.kind_source.as_str() {
                "manual" => 0,
                "provider" => 1,
                "url" => 2,
                _ => 3,
            };
            let chosen = origins.iter().min_by_key(|r| priority(r)).unwrap();
            let (kind, kind_source) = (chosen.kind.clone(), chosen.kind_source.clone());
            if !kinds.is_empty() && !kinds.contains(&kind) {
                return None;
            }
            Some(Book {
                id: origins[0].id(),
                url,
                title,
                kind,
                kind_source,
                origins,
            })
        })
        .collect()
}
pub fn revision(db: &Connection) -> Result<i64> {
    Ok(
        db.query_row("SELECT value FROM meta WHERE key='revision'", [], |r| {
            r.get(0)
        })?,
    )
}
pub fn vector(db: &Connection, body: &str) -> Result<Option<Vec<f32>>> {
    let mut q = db.prepare_cached("SELECT vector FROM vectors WHERE hash=?1 AND spec=?2")?;
    prepared_vector(&mut q, body)
}
pub fn prepared_vector(q: &mut rusqlite::Statement<'_>, body: &str) -> Result<Option<Vec<f32>>> {
    use rusqlite::OptionalExtension;
    let raw: Option<Vec<u8>> = q
        .query_row(params![hash(body), embedding::SPEC], |r| r.get(0))
        .optional()?;
    raw.map(|raw| {
        ensure!(raw.len() == embedding::DIM * 4, "Invalid cached embedding");
        let v: Vec<_> = raw
            .as_chunks::<4>()
            .0
            .iter()
            .map(|b| f32::from_le_bytes(*b))
            .collect();
        ensure!(
            v.iter().all(|x| x.is_finite()),
            "Nonfinite cached embedding"
        );
        Ok(v)
    })
    .transpose()
}
pub fn publish(
    db: &mut Connection,
    snapshots: &[(String, String, Vec<Record>)],
    expected: i64,
    semantic: bool,
    relations: Option<&[crate::graph::Relation]>,
) -> Result<usize> {
    ensure!(
        revision(db)? == expected,
        "Index changed during refresh; retry sync"
    );
    let mut all = state::records(db)?;
    for (provider, _, records) in snapshots {
        all.retain(|r| r.provider != *provider);
        all.extend(records.clone());
    }
    let mut bodies: BTreeMap<String, String> = BTreeMap::new();
    if semantic {
        for r in &all {
            bodies.insert(hash(r.body()), r.body());
            for p in crate::passage::record(r) {
                bodies.insert(hash(&p.text), p.text);
            }
        }
        for b in merge(all.clone(), &[], &[], None) {
            bodies.insert(hash(b.body()), b.body());
        }
        let mut missing = BTreeMap::new();
        for (hash, body) in bodies {
            if vector(db, &body)?.is_none() {
                missing.insert(hash, body);
            }
        }
        bodies = missing;
    }
    let (texts, vectors) = if !bodies.is_empty() {
        let texts: Vec<_> = bodies.into_values().collect();
        let vectors = Embedder::new()?.embed(&texts, false)?;
        (texts, vectors)
    } else {
        (Vec::new(), Vec::new())
    };
    let tx = db.transaction_with_behavior(rusqlite::TransactionBehavior::Immediate)?;
    ensure!(
        revision(&tx)? == expected,
        "Index changed during refresh; previous generation retained"
    );
    if let Some(relations) = relations {
        for r in relations {
            r.validate()?;
        }
        tx.execute("DELETE FROM relations", [])?;
        for r in relations {
            tx.execute(
                "INSERT INTO relations VALUES(?1,?2,?3,?4)",
                params![r.a, r.b, r.kind, r.suppressed],
            )?;
        }
    }
    for (provider, account, records) in snapshots {
        tx.execute("DELETE FROM records WHERE provider=?1", [provider])?;
        for r in records {
            tx.execute(
                "INSERT INTO records VALUES(?1,?2,?3)",
                params![r.origin(), r.provider, serde_json::to_string(r)?],
            )?;
        }
        tx.execute("INSERT INTO sources VALUES(?1,?2,unixepoch(),?3) ON CONFLICT(provider) DO UPDATE SET account=excluded.account,refreshed_at=excluded.refreshed_at,count=excluded.count",params![provider,account,records.len() as i64])?;
    }
    for (body, vector) in texts.iter().zip(vectors) {
        let blob: Vec<u8> = vector.into_iter().flat_map(f32::to_le_bytes).collect();
        tx.execute(
            "INSERT OR REPLACE INTO vectors VALUES(?1,?2,?3)",
            params![hash(body), embedding::SPEC, blob],
        )?;
    }
    tx.execute("UPDATE meta SET value=value+1 WHERE key='revision'", [])?;
    tx.commit()?;
    Ok(all.len())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn source_scope_and_exact_dedup() {
        let mut a = Record::new("raindrop", "me", "1", "https://openai.com/index/one/").unwrap();
        a.title = "One".into();
        let mut b = a.clone();
        b.provider = "instapaper".into();
        b.note = "private source term".into();
        let books = merge(vec![a.clone(), b.clone()], &[], &[], Some("openai.com"));
        assert_eq!(books.len(), 1);
        assert_eq!(books[0].origins.len(), 2);
        let books = merge(vec![a, b], &["raindrop".into()], &[], None);
        assert!(!books[0].body().contains("private source"));
    }
    #[test]
    fn stale_refresh_rejected() {
        let tmp = tempfile::tempdir().unwrap();
        let mut db = state::db(tmp.path()).unwrap();
        publish(&mut db, &[], 0, false, None).unwrap();
        assert!(publish(&mut db, &[], 0, false, None).is_err());
    }
}
