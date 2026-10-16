use crate::{
    embedding::{self, Embedder},
    graph::{self, Edge},
    index::{self, Book},
    lexical, passage, state,
};
use anyhow::{Result, ensure};
use rusqlite::Connection;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
#[derive(Clone, Default, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Filter {
    pub sources: Vec<String>,
    pub kinds: Vec<String>,
    pub domain: Option<String>,
}
impl Filter {
    pub fn validate(&mut self) -> Result<()> {
        ensure!(
            self.sources
                .iter()
                .all(|s| crate::model::PROVIDERS.contains(&s.as_str()))
                && self
                    .kinds
                    .iter()
                    .all(|k| crate::model::KINDS.contains(&k.as_str())),
            "Invalid source/type filter"
        );
        if let Some(d) = &mut self.domain {
            *d = d.to_lowercase();
            ensure!(
                d.chars()
                    .all(|c| c.is_ascii_alphanumeric() || c == '.' || c == '-'),
                "Expected a bare domain"
            );
            let u = url::Url::parse(&format!("https://{d}/"))
                .map_err(|_| anyhow::anyhow!("Invalid domain filter"))?;
            ensure!(
                u.host_str() == Some(d.as_str())
                    && u.path() == "/"
                    && u.port().is_none()
                    && u.username().is_empty()
                    && u.query().is_none()
                    && u.fragment().is_none(),
                "Expected a bare domain"
            );
        }
        Ok(())
    }
    pub fn books(&self, db: &Connection) -> Result<Vec<Book>> {
        Ok(index::merge(
            state::records(db)?,
            &self.sources,
            &self.kinds,
            self.domain.as_deref(),
        ))
    }
}
#[derive(Clone, Serialize)]
pub struct Hit {
    #[serde(flatten)]
    pub book: Book,
    pub rank: usize,
    pub score: f32,
    pub cosine: Option<f32>,
    pub matched_by: Vec<String>,
    pub graph_path: Option<Vec<Edge>>,
    pub passage: Option<passage::Passage>,
}
#[derive(Serialize)]
pub struct Results {
    pub generation: i64,
    pub hits: Vec<Hit>,
    pub total: usize,
    pub strategy: &'static str,
    pub passage_index: &'static str,
}
pub fn search(
    db: &mut Connection,
    query: &str,
    filter: &Filter,
    limit: usize,
    semantic: bool,
    assisted: bool,
) -> Result<Results> {
    ensure!(
        !query.trim().is_empty() && query.len() <= 4096 && (1..=10000).contains(&limit),
        "Invalid query/limit"
    );
    let tx = db.transaction()?;
    let generation = index::revision(&tx)?;
    let books = filter.books(&tx)?;
    if books.is_empty() {
        tx.rollback()?;
        return Ok(Results {
            generation,
            hits: Vec::new(),
            total: 0,
            strategy: "lexical",
            passage_index: "not-used",
        });
    }
    let mut tokens = lexical::terms(query);
    tokens.sort();
    tokens.dedup();
    let ranking = lexical::rank(&books, &tokens);
    let mut lexical = Vec::new();
    let mut semantic_scores = Vec::new();
    let precise = ranking.navigation || ranking.exact_title || tokens.len() <= 1;
    let qvec = if semantic && !precise {
        Some(Embedder::new()?.embed(&[query.into()], true)?.remove(0))
    } else {
        None
    };
    let mut passages = Vec::with_capacity(books.len());
    let mut missing_passages = 0;
    let mut vectors = tx.prepare_cached("SELECT vector FROM vectors WHERE hash=?1 AND spec=?2")?;
    for (i, b) in books.iter().enumerate() {
        let lex = ranking.scores[i];
        if lex > 0. {
            lexical.push((i, lex));
        }
        let mut best_passage = None;
        let mut best_evidence = 0.;
        let mut passage_cosine: Option<f32> = None;
        for mut p in b.origins.iter().flat_map(passage::record) {
            let evidence = lexical::passage_score(&p.text, &tokens, &ranking.idf);
            if let Some(q) = &qvec {
                if let Some(v) = index::prepared_vector(&mut vectors, &p.text)? {
                    let cos = embedding::dot(q, &v);
                    p.cosine = Some(cos);
                    passage_cosine = Some(passage_cosine.map_or(cos, |old| old.max(cos)));
                    if cos >= 0.25
                        && best_passage
                            .as_ref()
                            .is_none_or(|old: &passage::Passage| old.cosine.is_none_or(|s| cos > s))
                    {
                        best_passage = Some(p.clone());
                    }
                } else {
                    missing_passages += 1;
                }
            }
            if evidence > best_evidence
                && best_passage.as_ref().is_none_or(|old| old.cosine.is_none())
            {
                best_evidence = evidence;
                best_passage = Some(p);
            }
        }
        passages.push(best_passage);
        if let Some(q) = &qvec {
            let vector = index::prepared_vector(&mut vectors, &b.body())?;
            let score = if let Some(v) = vector {
                Some(embedding::dot(q, &v))
            } else {
                let mut best: Option<f32> = None;
                for r in &b.origins {
                    if let Some(v) = index::prepared_vector(&mut vectors, &r.body())? {
                        let s = embedding::dot(q, &v);
                        best = Some(best.map_or(s, |b| b.max(s)));
                    }
                }
                best
            };
            ensure!(
                score.is_some(),
                "Semantic index incomplete; run bkd sync (refresh and index) or bkd sync --offline (cached data only)"
            );
            semantic_scores.push((
                i,
                passage_cosine.map_or(score.unwrap(), |p| p.max(score.unwrap())),
            ));
        }
    }
    drop(vectors);
    lexical.sort_by(|a, b| b.1.total_cmp(&a.1).then(a.0.cmp(&b.0)));
    semantic_scores.sort_by(|a, b| b.1.total_cmp(&a.1).then(a.0.cmp(&b.0)));
    // Provisional conservative gate when no literal evidence anchors the query.
    let semantic_minimum = if lexical.is_empty() { 0.60 } else { 0.45 };
    let mut scores: BTreeMap<usize, Hit> = BTreeMap::new();
    for (method, ranks) in [
        (
            "lexical",
            lexical.iter().map(|(i, _)| *i).collect::<Vec<_>>(),
        ),
        (
            "semantic",
            semantic_scores
                .iter()
                .filter(|(_, s)| *s >= semantic_minimum)
                .map(|(i, _)| *i)
                .collect(),
        ),
    ] {
        for (rank, i) in ranks.into_iter().take(100).enumerate() {
            let hit = scores.entry(i).or_insert(Hit {
                book: books[i].clone(),
                rank: 0,
                score: 0.,
                cosine: semantic_scores
                    .iter()
                    .find(|(j, _)| *j == i)
                    .map(|(_, s)| *s),
                matched_by: Vec::new(),
                graph_path: None,
                passage: passages[i].clone(),
            });
            hit.score += 1. / (61. + rank as f32);
            hit.matched_by.push(method.into());
        }
    }
    if assisted && !ranking.navigation && !ranking.exact_title {
        let graph = graph::derive(&tx, &books, false)?;
        let mut seeds: Vec<_> = scores.iter().map(|(&i, h)| (i, h.score)).collect();
        seeds.sort_by(|a, b| b.1.total_cmp(&a.1));
        seeds.truncate(20);
        let mut support: BTreeMap<usize, (f32, Vec<Edge>)> = BTreeMap::new();
        graph_support(
            &graph,
            &books,
            &seeds,
            &ranking.scores,
            &semantic_scores,
            &mut support,
        );
        for (i, (boost, path)) in support {
            let h = scores.entry(i).or_insert(Hit {
                book: books[i].clone(),
                rank: 0,
                score: 0.,
                cosine: semantic_scores
                    .iter()
                    .find(|(j, _)| *j == i)
                    .map(|(_, s)| *s),
                matched_by: Vec::new(),
                graph_path: None,
                passage: passages[i].clone(),
            });
            h.score += boost;
            h.matched_by.push("graph".into());
            h.graph_path = Some(path);
        }
    }
    let mut hits: Vec<_> = scores.into_values().collect();
    hits.sort_by(|a, b| b.score.total_cmp(&a.score).then(a.book.id.cmp(&b.book.id)));
    hits.truncate(limit);
    for (i, h) in hits.iter_mut().enumerate() {
        h.rank = i + 1;
    }
    tx.rollback()?;
    Ok(Results {
        generation,
        hits,
        total: books.len(),
        strategy: if ranking.navigation {
            "navigation"
        } else if ranking.exact_title {
            "exact-title"
        } else if qvec.is_some() {
            "hybrid"
        } else {
            "lexical"
        },
        passage_index: if qvec.is_none() {
            "not-used"
        } else if missing_passages == 0 {
            "complete"
        } else {
            "partial"
        },
    })
}

fn graph_support(
    graph: &graph::Graph,
    books: &[Book],
    seeds: &[(usize, f32)],
    lexical: &[f32],
    cosine: &[(usize, f32)],
    support: &mut BTreeMap<usize, (f32, Vec<Edge>)>,
) {
    use std::collections::{BTreeSet, VecDeque};
    let byid: BTreeMap<_, _> = books
        .iter()
        .enumerate()
        .map(|(i, b)| (b.id.as_str(), i))
        .collect();
    let mut adjacent: BTreeMap<&str, Vec<(&str, &Edge)>> = BTreeMap::new();
    for edge in &graph.edges {
        if edge.status == "inferred" {
            continue;
        }
        adjacent.entry(&edge.a).or_default().push((&edge.b, edge));
        if edge.kind != "mentions" {
            adjacent.entry(&edge.b).or_default().push((&edge.a, edge));
        }
    }
    let mut budget = 5000usize;
    for &(seed, seed_score) in seeds {
        let start = books[seed].id.as_str();
        let mut queue = VecDeque::from([(
            start,
            1f32,
            Vec::<Edge>::new(),
            0usize,
            BTreeSet::from([start]),
        )]);
        while let Some((node, strength, path, hops, seen)) = queue.pop_front() {
            for &(next, edge) in adjacent.get(node).into_iter().flatten() {
                if budget == 0 {
                    return;
                }
                budget -= 1;
                if seen.contains(next) {
                    continue;
                }
                let weight = match edge.kind.as_str() {
                    "related" => 1.,
                    "mentions" => 0.85,
                    "tag" | "collection" => 0.6,
                    _ => continue,
                };
                let degree = adjacent.get(node).map_or(1, Vec::len).max(1) as f32;
                let strength = strength * weight / degree.sqrt();
                let mut path = path.clone();
                path.push(edge.clone());
                let mut seen = seen.clone();
                seen.insert(next);
                let mut hops = hops;
                if let Some(&i) = byid.get(next) {
                    if lexical[i] == 0.
                        && cosine
                            .iter()
                            .find(|(j, _)| *j == i)
                            .is_none_or(|(_, s)| *s < 0.45)
                    {
                        continue;
                    }
                    hops += 1;
                    let boost = seed_score * 0.15 * strength * 0.5f32.powi((hops - 1) as i32);
                    if support.get(&i).is_none_or(|(old, _)| boost > *old) {
                        support.insert(i, (boost, path.clone()));
                    }
                }
                if hops < 2 && path.len() < 4 {
                    queue.push_back((next, strength, path, hops, seen));
                }
            }
        }
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn two_hop_support_retains_direction_evidence_and_query_gate() {
        use crate::model::Record;
        let books = index::merge(
            (0..4)
                .map(|i| {
                    Record::new(
                        "manual",
                        "fixture",
                        &i.to_string(),
                        &format!("https://example.org/{i}"),
                    )
                    .unwrap()
                })
                .collect(),
            &[],
            &[],
            None,
        );
        let mut graph = graph::bookmarks(1, &books);
        let edge = |a: usize, b: usize, status: &str, kind: &str| Edge {
            a: books[a].id.clone(),
            b: books[b].id.clone(),
            kind: kind.into(),
            status: status.into(),
            evidence: serde_json::json!({"fixture":"retained"}),
        };
        graph.edges = vec![
            edge(0, 1, "user", "related"),
            edge(1, 2, "recorded", "mentions"),
            edge(0, 3, "inferred", "similar"),
        ];
        let mut support = BTreeMap::new();
        graph_support(
            &graph,
            &books,
            &[(0, 1.)],
            &[1., 1., 1., 1.],
            &[],
            &mut support,
        );
        assert_eq!(support[&2].1.len(), 2);
        assert_eq!(support[&2].1[1].evidence["fixture"], "retained");
        assert!(support.values().all(|(score, _)| *score <= 0.15));
        assert!(!support.contains_key(&3));
        support.clear();
        graph_support(&graph, &books, &[(2, 1.)], &[1.; 4], &[], &mut support);
        assert!(
            support.is_empty(),
            "mentions must not become reverse citations"
        );
        graph_support(
            &graph,
            &books,
            &[(0, 1.)],
            &[1., 0., 1., 1.],
            &[],
            &mut support,
        );
        assert!(
            !support.contains_key(&2),
            "irrelevant intermediate bookmarks cannot propagate"
        );
    }
    #[test]
    fn passage_evidence_is_exact_and_source_scoped() {
        let tmp = tempfile::tempdir().unwrap();
        let mut db = state::db(tmp.path()).unwrap();
        let mut r =
            crate::model::Record::new("raindrop", "fixture", "1", "https://example.org/notes")
                .unwrap();
        r.note = format!(
            "{}\nTarget quantum evidence.\n",
            "研究 background ".repeat(80)
        );
        let mut excluded = r.clone();
        excluded.provider = "instapaper".into();
        excluded.note = "hiddenkeyword".into();
        index::publish(
            &mut db,
            &[
                ("raindrop".into(), "fixture".into(), vec![r.clone()]),
                ("instapaper".into(), "fixture".into(), vec![excluded]),
            ],
            0,
            false,
            None,
        )
        .unwrap();
        let result = search(
            &mut db,
            "target quantum",
            &Filter {
                sources: vec!["raindrop".into()],
                ..Default::default()
            },
            10,
            false,
            true,
        )
        .unwrap();
        let p = result.hits[0].passage.as_ref().unwrap();
        assert_eq!(p.text, r.note[p.start..p.end]);
        assert_eq!(p.provider, "raindrop");
        assert!(p.text.contains("Target quantum"));
        assert!(
            search(
                &mut db,
                "hiddenkeyword",
                &Filter {
                    sources: vec!["raindrop".into()],
                    ..Default::default()
                },
                10,
                false,
                true
            )
            .unwrap()
            .hits
            .is_empty()
        );
    }
    #[test]
    fn selected_sources_do_not_vote_and_graph_support_is_bounded() {
        let tmp = tempfile::tempdir().unwrap();
        let mut db = state::db(tmp.path()).unwrap();
        let mut a =
            crate::model::Record::new("raindrop", "me", "a", "https://openai.com/index/one/")
                .unwrap();
        a.title = "Database research".into();
        a.tags = vec!["shared".into()];
        let mut b = a.clone();
        b.external_id = "b".into();
        b.url = "https://openai.com/index/two/".into();
        b.title = "Research methods".into();
        let mut other = a.clone();
        other.provider = "instapaper".into();
        other.note = "zebrasecret".into();
        index::publish(
            &mut db,
            &[
                ("raindrop".into(), "me".into(), vec![a.clone(), b]),
                ("instapaper".into(), "me".into(), vec![other]),
            ],
            0,
            false,
            None,
        )
        .unwrap();
        let f = Filter {
            sources: vec!["raindrop".into()],
            ..Default::default()
        };
        assert!(
            search(&mut db, "zebrasecret", &f, 20, false, true)
                .unwrap()
                .hits
                .is_empty()
        );
        let baseline = search(&mut db, "research", &f, 20, false, false).unwrap();
        let assisted = search(&mut db, "research", &f, 20, false, true).unwrap();
        for h in assisted.hits {
            let base = baseline
                .hits
                .iter()
                .find(|x| x.book.id == h.book.id)
                .unwrap();
            assert!(h.score <= base.score + baseline.hits[0].score * 0.15001);
            assert!(h.book.origins.iter().all(|r| r.provider == "raindrop"));
        }
        assert_eq!(baseline.generation, 1);
    }
    #[test]
    #[ignore = "Requires the pinned local BGE model and llama-embedding"]
    fn real_local_model_retrieval() {
        let tmp = tempfile::tempdir().unwrap();
        let mut db = state::db(tmp.path()).unwrap();
        let mut research = crate::model::Record::new(
            "instapaper",
            "me",
            "r",
            "https://openai.com/index/interpretability-research/",
        )
        .unwrap();
        research.title = "Research into sparse autoencoders".into();
        research.excerpt="Interpretability research: extracting interpretable features from transformer neural networks.".into();
        research.tags = vec!["research".into()];
        let mut product = crate::model::Record::new(
            "raindrop",
            "me",
            "p",
            "https://openai.com/index/subscription/",
        )
        .unwrap();
        product.title = "Introducing a subscription plan".into();
        product.excerpt = "Pricing and billing updates for customers.".into();
        let mut copy = research.clone();
        copy.provider = "raindrop".into();
        copy.external_id = "copy".into();
        index::publish(
            &mut db,
            &[
                ("instapaper".into(), "me".into(), vec![research.clone()]),
                ("raindrop".into(), "me".into(), vec![product, copy]),
            ],
            0,
            true,
            None,
        )
        .unwrap();
        let f = Filter {
            domain: Some("openai.com".into()),
            kinds: vec!["blog".into()],
            ..Default::default()
        };
        let result = search(
            &mut db,
            "How can we interpret features inside neural networks?",
            &f,
            20,
            true,
            true,
        )
        .unwrap();
        assert_eq!(result.hits[0].book.id, research.id());
        assert_eq!(result.hits[0].book.origins.len(), 2);
        assert!(result.hits[0].cosine.unwrap() > 0.45);
    }
    #[test]
    fn rejects_domain_confusion() {
        for d in [
            "openai.com/evil",
            "u@openai.com",
            "openai.com:443",
            "openai.com?x=y",
        ] {
            assert!(
                Filter {
                    domain: Some(d.into()),
                    ..Default::default()
                }
                .validate()
                .is_err()
            );
        }
        assert!(
            Filter {
                domain: Some("openai.com".into()),
                ..Default::default()
            }
            .validate()
            .is_ok()
        );
    }
}
