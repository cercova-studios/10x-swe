use crate::{embedding, index, index::Book, model::hash};
use anyhow::{Result, ensure};
use rusqlite::{Connection, params};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet, VecDeque};

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Node {
    pub id: String,
    pub label: String,
    pub kind: String,
    pub url: Option<String>,
    pub bookmark_kind: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub details: Option<serde_json::Value>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Edge {
    pub a: String,
    pub b: String,
    pub kind: String,
    pub status: String,
    pub evidence: serde_json::Value,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Graph {
    pub generation: i64,
    pub nodes: Vec<Node>,
    pub edges: Vec<Edge>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub knowledge: Option<serde_json::Value>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Relation {
    pub a: String,
    pub b: String,
    pub kind: String,
    pub suppressed: bool,
}
impl Relation {
    pub fn validate(&self) -> Result<()> {
        ensure!(
            self.a.len() == 64
                && self.b.len() == 64
                && self.a < self.b
                && [&self.a, &self.b].iter().all(|s| s
                    .chars()
                    .all(|c| c.is_ascii_hexdigit() && !c.is_ascii_uppercase()))
                && ["related", "similar"].contains(&self.kind.as_str())
                && (self.kind != "similar" || self.suppressed),
            "Invalid relationship"
        );
        Ok(())
    }
}
fn mention_offset(text: &str, url: &str) -> Option<usize> {
    text.match_indices(url).find_map(|(offset, _)| {
        let before = text[..offset].chars().next_back();
        let after = text[offset + url.len()..].chars().next();
        let left = before.is_none_or(|c| c.is_whitespace() || ['"', '(', '[', '<'].contains(&c));
        let right = after.is_none_or(|c| c.is_whitespace() || ['"', ')', ']', '>'].contains(&c));
        (left && right).then_some(offset)
    })
}
pub fn bookmarks<'a>(generation: i64, books: impl IntoIterator<Item = &'a Book>) -> Graph {
    Graph {
        generation,
        nodes: books
            .into_iter()
            .map(|b| Node {
                id: b.id.clone(),
                label: b.title.clone(),
                kind: "bookmark".into(),
                url: Some(b.url.clone()),
                bookmark_kind: Some(b.kind.clone()),
                details: None,
            })
            .collect(),
        edges: Vec::new(),
        knowledge: None,
    }
}
fn mention_offsets(
    text: &str,
    urls: &BTreeMap<&str, usize>,
    max_url_len: usize,
) -> BTreeMap<usize, usize> {
    let mut found = BTreeMap::new();
    let mut left_boundary = true;
    for (offset, c) in text.char_indices() {
        let eligible = left_boundary;
        left_boundary = c.is_whitespace() || ['"', '(', '[', '<'].contains(&c);
        if !eligible || !matches!(c, 'h' | 'H') {
            continue;
        }
        let tail = &text[offset..];
        if !tail
            .get(..7)
            .is_some_and(|s| s.eq_ignore_ascii_case("http://"))
            && !tail
                .get(..8)
                .is_some_and(|s| s.eq_ignore_ascii_case("https://"))
        {
            continue;
        }
        for (end, c) in tail
            .char_indices()
            .chain(std::iter::once((tail.len(), ' ')))
        {
            if end > max_url_len {
                break;
            }
            if (c.is_whitespace() || ['"', ')', ']', '>'].contains(&c))
                && let Some(&index) = urls.get(&tail[..end])
                && !found.contains_key(&index)
                && let Some(first) = mention_offset(text, &tail[..end])
            {
                found.insert(index, first);
            }
            if c.is_whitespace() {
                break;
            }
        }
    }
    found
}
fn similar_neighbors(vectors: &[Option<Vec<f32>>]) -> Result<Vec<Vec<(usize, f32)>>> {
    let mut nearest = vec![Vec::new(); vectors.len()];
    let workers = std::thread::available_parallelism()
        .map_or(1, usize::from)
        .min(8)
        .min(vectors.len().div_ceil(128).max(1));
    let chunk = vectors.len().div_ceil(workers).max(1);
    // Independent rows retain the scalar accumulation and ascending tie order.
    std::thread::scope(|scope| -> Result<()> {
        for (block, rows) in nearest.chunks_mut(chunk).enumerate() {
            std::thread::Builder::new().spawn_scoped(scope, move || {
                for (offset, near) in rows.iter_mut().enumerate() {
                    let i = block * chunk + offset;
                    let Some(a) = &vectors[i] else { continue };
                    for (j, b) in vectors.iter().enumerate() {
                        if i == j {
                            continue;
                        }
                        if let Some(b) = b {
                            let score = embedding::dot(a, b);
                            if score >= 0.78 {
                                near.push((j, score));
                                near.sort_by(|a, b| b.1.total_cmp(&a.1));
                                near.truncate(6);
                            }
                        }
                    }
                }
            })?;
        }
        Ok(())
    })?;
    Ok(nearest)
}
pub fn derive(db: &Connection, books: &[Book], similarity: bool) -> Result<Graph> {
    let urls: BTreeMap<_, _> = books
        .iter()
        .enumerate()
        .map(|(i, b)| (b.url.as_str(), i))
        .collect();
    let max_url_len = urls.keys().map(|url| url.len()).max().unwrap_or(0);

    let base = bookmarks(index::revision(db)?, books);
    let mut nodes: BTreeMap<String, Node> =
        base.nodes.into_iter().map(|n| (n.id.clone(), n)).collect();
    let mut edges: BTreeMap<(String, String, String), Edge> = BTreeMap::new();
    let mut add = |a: String, b: String, kind: &str, status: &str, evidence: serde_json::Value| {
        edges.insert(
            (a.clone(), b.clone(), kind.into()),
            Edge {
                a,
                b,
                kind: kind.into(),
                status: status.into(),
                evidence,
            },
        );
    };
    for book in books {
        for r in &book.origins {
            for (kind, label) in r
                .tags
                .iter()
                .map(|t| ("tag", t))
                .chain((!r.folder.is_empty()).then_some(("collection", &r.folder)))
            {
                let hub = hash(serde_json::to_vec(&(kind, &r.provider, &r.account, label))?);
                nodes.entry(hub.clone()).or_insert(Node {
                    id: hub.clone(),
                    label: format!("{} · {}", r.provider, label),
                    kind: kind.into(),
                    url: None,
                    bookmark_kind: None,
                    details: None,
                });
                add(
                    book.id.clone(),
                    hub,
                    kind,
                    "recorded",
                    serde_json::json!({"provider":r.provider,"account":r.account,"value":label}),
                );
            }
            for (field, text) in [("note", &r.note), ("excerpt", &r.excerpt)] {
                for (i, offset) in mention_offsets(text, &urls, max_url_len) {
                    let other = &books[i];
                    if other.id != book.id {
                        add(
                            book.id.clone(),
                            other.id.clone(),
                            "mentions",
                            "recorded",
                            serde_json::json!({"provider":r.provider,"field":field,"offset":offset,"hash":hash(text)}),
                        );
                    }
                }
            }
        }
    }
    let mut suppressed = BTreeSet::new();
    let mut q = db.prepare("SELECT a,b,kind,suppressed FROM relations")?;
    let rows = q.query_map([], |r| {
        Ok((
            r.get::<_, String>(0)?,
            r.get::<_, String>(1)?,
            r.get::<_, String>(2)?,
            r.get::<_, bool>(3)?,
        ))
    })?;
    for row in rows {
        let (a, b, kind, s) = row?;
        if s {
            suppressed.insert((a.clone(), b.clone(), kind));
        } else if nodes.contains_key(&a) && nodes.contains_key(&b) {
            add(
                a,
                b,
                "related",
                "user",
                serde_json::json!({"method":"authored"}),
            );
        }
    }
    if similarity {
        let vectors = books
            .iter()
            .map(|b| index::vector(db, &b.body()))
            .collect::<Result<Vec<_>>>()?;
        let nearest = similar_neighbors(&vectors)?;
        for (i, near) in nearest.iter().enumerate() {
            for &(j, score) in near {
                if i < j && nearest[j].iter().any(|&(k, _)| k == i) {
                    let (a, b) = if books[i].id < books[j].id {
                        (&books[i], &books[j])
                    } else {
                        (&books[j], &books[i])
                    };
                    if !suppressed.contains(&(a.id.clone(), b.id.clone(), "similar".into())) {
                        add(
                            a.id.clone(),
                            b.id.clone(),
                            "similar",
                            "inferred",
                            serde_json::json!({"cosine":score,"method":"mutual-knn-6","spec":embedding::SPEC,"hashes":[hash(a.body()),hash(b.body())]}),
                        );
                    }
                }
            }
        }
    }
    Ok(Graph {
        generation: base.generation,
        nodes: nodes.into_values().collect(),
        edges: edges.into_values().collect(),
        knowledge: None,
    })
}
impl Graph {
    pub fn adjacent(&self, id: &str) -> Vec<(&str, &Edge)> {
        self.edges
            .iter()
            .filter_map(|e| {
                if e.a == id {
                    Some((e.b.as_str(), e))
                } else if e.b == id && e.kind != "mentions" {
                    Some((e.a.as_str(), e))
                } else {
                    None
                }
            })
            .collect()
    }
    pub fn neighbors(&self, id: &str) -> Vec<(String, Vec<Edge>)> {
        let types: BTreeMap<_, _> = self
            .nodes
            .iter()
            .map(|n| (n.id.as_str(), n.kind.as_str()))
            .collect();
        let mut out = BTreeMap::new();
        let mut budget = 2000;
        for (next, e) in self.adjacent(id) {
            if budget == 0 {
                break;
            }
            budget -= 1;
            if types.get(next) == Some(&"bookmark") {
                out.entry(next.into()).or_insert(vec![e.clone()]);
            } else {
                for (last, second) in self.adjacent(next) {
                    if budget == 0 {
                        break;
                    }
                    budget -= 1;
                    if last != id && types.get(last) == Some(&"bookmark") {
                        out.entry(last.into())
                            .or_insert(vec![e.clone(), second.clone()]);
                    }
                }
            }
        }
        out.into_iter().collect()
    }
    pub fn path(&self, a: &str, b: &str) -> Option<Vec<Edge>> {
        let mut queue = VecDeque::from([(a.to_owned(), Vec::<Edge>::new())]);
        let mut seen = BTreeSet::from([a.to_owned()]);
        let mut work = 0;
        while let Some((node, path)) = queue.pop_front() {
            if node == b {
                return Some(path);
            }
            if path.len() >= 6 {
                continue;
            }
            for (next, e) in self.adjacent(&node) {
                work += 1;
                if work > 5000 {
                    return None;
                }
                if seen.insert(next.into()) {
                    let mut p = path.clone();
                    p.push(e.clone());
                    queue.push_back((next.into(), p));
                }
            }
        }
        None
    }
}
pub fn relate(
    db: &mut Connection,
    a: &str,
    b: &str,
    kind: &str,
    remove: bool,
    suppressed: bool,
) -> Result<()> {
    ensure!(
        a.len() == 64
            && b.len() == 64
            && a != b
            && [a, b].iter().all(|s| s
                .chars()
                .all(|c| c.is_ascii_hexdigit() && !c.is_ascii_uppercase()))
            && ["related", "similar"].contains(&kind),
        "Invalid relationship"
    );
    let (a, b) = if a < b { (a, b) } else { (b, a) };
    let tx = db.transaction()?;
    if remove {
        tx.execute(
            "DELETE FROM relations WHERE a=?1 AND b=?2 AND kind=?3",
            params![a, b, kind],
        )?;
    } else {
        tx.execute("INSERT INTO relations VALUES(?1,?2,?3,?4) ON CONFLICT(a,b,kind) DO UPDATE SET suppressed=excluded.suppressed",params![a,b,kind,suppressed])?;
    }
    tx.execute("UPDATE meta SET value=value+1 WHERE key='revision'", [])?;
    tx.commit()?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn parallel_similarity_matches_sequential_scores_and_ties() {
        let vectors: Vec<_> = (0..257)
            .map(|i| {
                if i % 19 == 0 {
                    return None;
                }
                let mut v = vec![0.; embedding::DIM];
                match i % 5 {
                    0 => v[0] = 1.,
                    1 => v[0] = 0.78,
                    2 => v[0] = f32::from_bits(0.78f32.to_bits() - 1),
                    3 => v[0] = f32::from_bits(0.78f32.to_bits() + 1),
                    _ => {
                        for (j, value) in v.iter_mut().enumerate() {
                            *value = ((i * 17 + j * 31) % 101) as f32 / 100.;
                        }
                        embedding::normalize(&mut v).unwrap();
                    }
                }
                Some(v)
            })
            .collect();
        for len in [0, 1, 127, 128, 129, 257] {
            let vectors = &vectors[..len];
            let mut expected = vec![Vec::<(usize, f32)>::new(); len];
            for (i, a) in vectors.iter().enumerate() {
                let Some(a) = a else { continue };
                for (j, b) in vectors.iter().enumerate() {
                    if i == j {
                        continue;
                    }
                    if let Some(b) = b {
                        let score = embedding::dot(a, b);
                        if score >= 0.78 {
                            expected[i].push((j, score));
                            expected[i].sort_by(|a, b| b.1.total_cmp(&a.1));
                            expected[i].truncate(6);
                        }
                    }
                }
            }
            assert_eq!(
                similar_neighbors(vectors).unwrap(),
                expected,
                "length {len}"
            );
        }
    }
    #[test]
    fn indexed_mentions_match_pairwise_oracle() {
        let urls = [
            "https://saved.org/item",
            "https://saved.org/item?other=true",
            "https://saved.org/item)extra",
            "https://saved.org/item(https://nested.org/x)",
            "https://nested.org/x",
            "HTTP://saved.org/Upper",
            "https://saved.org/研究",
            "https://x/(https://x/(",
        ];
        let lookup: BTreeMap<_, _> = urls.iter().enumerate().map(|(i, &u)| (u, i)).collect();
        let max_len = urls.iter().map(|u| u.len()).max().unwrap();
        let mut texts = vec![
            "https://evil.org/https://saved.org/item".to_owned(),
            "研究 [x](https://saved.org/研究) then HTTP://saved.org/Upper".to_owned(),
            "https://saved.org/item)extra https://saved.org/item(https://nested.org/x)".to_owned(),
            "https://saved.org/item?other=true https://saved.org/item".to_owned(),
            "https://saved.org/item. https://saved.org/item".to_owned(),
            "".to_owned(),
            "https://x/(https://x/(https://x/()".to_owned(),
        ];
        for url in urls {
            for left in [
                "", " ", "\n", "\u{2003}", "\"", "(", "[", "<", "x", "/", "研究",
            ] {
                for right in [
                    "", " ", "\n", "\u{2003}", "\"", ")", "]", ">", "?x=1", "/more", ".", "研究",
                ] {
                    texts.push(format!("{left}{url}{right}"));
                }
            }
        }
        for text in texts {
            let expected: BTreeMap<_, _> = urls
                .iter()
                .enumerate()
                .filter_map(|(i, url)| mention_offset(&text, url).map(|offset| (i, offset)))
                .collect();
            assert_eq!(mention_offsets(&text, &lookup, max_len), expected, "{text}");
        }
    }
    #[test]
    fn mentions_require_both_url_boundaries() {
        assert!(
            mention_offset(
                "https://evil.org/https://saved.org/item",
                "https://saved.org/item"
            )
            .is_none()
        );
        assert_eq!(
            mention_offset("See [x](https://saved.org/item)", "https://saved.org/item"),
            Some(8)
        );
        assert!(
            mention_offset(
                "https://saved.org/item?other=true",
                "https://saved.org/item"
            )
            .is_none()
        );
    }
    use crate::{index, model::Record, state};
    #[test]
    fn scoped_tags_and_paths() {
        let tmp = tempfile::tempdir().unwrap();
        let db = state::db(tmp.path()).unwrap();
        let mut a = Record::new("raindrop", "me", "1", "https://a.com").unwrap();
        a.tags = vec!["research".into()];
        let mut b = Record::new("raindrop", "me", "2", "https://b.com").unwrap();
        b.tags = a.tags.clone();
        let mut c = Record::new("instapaper", "me", "3", "https://c.com").unwrap();
        c.tags = a.tags.clone();
        let (ai, bi, ci) = (a.id(), b.id(), c.id());
        let books = index::merge(vec![a, b, c], &[], &[], None);
        let g = derive(&db, &books, false).unwrap();
        assert_eq!(g.path(&ai, &bi).unwrap().len(), 2);
        assert!(g.path(&ai, &ci).is_none());
    }
    #[test]
    fn mention_evidence_retains_field_offset_and_source_scope() {
        let tmp = tempfile::tempdir().unwrap();
        let db = state::db(tmp.path()).unwrap();
        let mut a = Record::new("raindrop", "me", "1", "https://a.com").unwrap();
        let b = Record::new("raindrop", "me", "2", "https://b.com").unwrap();
        a.note = "See https://b.com and https://b.com".into();
        a.excerpt = "研究 (https://b.com)".into();
        let mut excluded = a.clone();
        excluded.provider = "instapaper".into();
        excluded.note = "See https://c.com".into();
        let c = Record::new("raindrop", "me", "3", "https://c.com").unwrap();
        let books = index::merge(
            vec![a.clone(), b.clone(), c.clone(), excluded],
            &["raindrop".into()],
            &[],
            None,
        );
        let g = derive(&db, &books, false).unwrap();
        assert_eq!(g.edges.len(), 1);
        let edge = &g.edges[0];
        assert_eq!((&edge.a, &edge.b), (&a.id(), &b.id()));
        assert_eq!(
            edge.evidence,
            serde_json::json!({"provider":"raindrop","field":"excerpt","offset":8,"hash":hash(&a.excerpt)})
        );
        assert!(g.path(&a.id(), &c.id()).is_none());
    }
}
