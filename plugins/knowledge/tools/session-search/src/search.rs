use crate::{
    model::{Hit, SearchResult, StrategyUnavailable},
    store::Store,
};
use anyhow::Result;
use std::collections::{BTreeMap, BTreeSet};
pub struct Query<'a> {
    pub text: &'a str,
    pub agent: Option<&'a str>,
    pub since: Option<i64>,
    pub limit: usize,
    pub last: bool,
}
fn one(store: &Store, q: &Query<'_>, mode: &str) -> Result<Vec<Hit>> {
    Ok(match mode {
        "naive" => store.lexical(q.text, q.agent, q.since, q.limit, q.last)?,
        "onto" => {
            if store.count("insights")? == 0 {
                return Err(StrategyUnavailable(
                    mode.into(),
                    "no insight graph; run session-search index".into(),
                )
                .into());
            }
            store.onto(q.text, q.agent, q.since, q.limit, q.last)?
        }
        "semantic" => {
            if store.count("embeddings")? == 0 {
                return Err(StrategyUnavailable(
                    mode.into(),
                    "no embeddings; run session-search index".into(),
                )
                .into());
            }
            store.semantic(q.text, q.agent, q.since, q.limit, q.last)?
        }
        _ => unreachable!(),
    })
}
pub fn run(store: &Store, q: Query<'_>, mode: &str) -> Result<SearchResult> {
    let mut result = SearchResult {
        query: q.text.into(),
        mode: mode.into(),
        hits: Vec::new(),
        strategies_used: Vec::new(),
        strategies_skipped: BTreeMap::new(),
    };
    if mode != "auto" {
        result.hits = one(store, &q, mode)?;
        result.strategies_used.push(mode.into());
        return Ok(result);
    }
    match one(store, &q, "onto") {
        Ok(hits) => {
            result.hits = hits;
            result.strategies_used.push("onto".into());
        }
        Err(e) => {
            if let Some(e) = e.downcast_ref::<StrategyUnavailable>() {
                result.strategies_skipped.insert(e.0.clone(), e.1.clone());
            } else {
                return Err(e);
            }
        }
    }
    let mut seen = result
        .hits
        .iter()
        .map(|h| h.id.clone())
        .collect::<BTreeSet<_>>();
    for hit in one(store, &q, "naive")? {
        if seen.insert(hit.id.clone()) {
            result.hits.push(hit)
        }
    }
    result.strategies_used.push("naive".into());
    if !q.last && result.hits.len() < 3 {
        match one(store, &q, "semantic") {
            Ok(hits) => {
                result.strategies_used.push("semantic".into());
                for hit in hits {
                    if seen.insert(hit.id.clone()) {
                        result.hits.push(hit)
                    }
                }
            }
            Err(e) => {
                if let Some(e) = e.downcast_ref::<StrategyUnavailable>() {
                    result.strategies_skipped.insert(e.0.clone(), e.1.clone());
                } else {
                    return Err(e);
                }
            }
        }
    } else {
        result
            .strategies_skipped
            .insert("semantic".into(), "not needed (naive/onto recall)".into());
    }
    if q.last {
        result.hits.sort_by_key(|h| std::cmp::Reverse(h.updated_at));
    }
    result.hits.truncate(q.limit);
    Ok(result)
}
