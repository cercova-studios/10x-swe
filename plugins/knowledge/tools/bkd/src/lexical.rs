use crate::index::Book;
use std::collections::BTreeSet;

pub fn terms(s: &str) -> Vec<String> {
    s.to_lowercase()
        .split(|c: char| !c.is_alphanumeric())
        .filter(|t| {
            t.len() > 1
                && ![
                    "the",
                    "and",
                    "for",
                    "from",
                    "with",
                    "what",
                    "how",
                    "are",
                    "that",
                    "this",
                    "all",
                    "bookmarks",
                    "import",
                    "posts",
                ]
                .contains(t)
        })
        .map(str::to_owned)
        .collect()
}

pub struct Ranking {
    pub scores: Vec<f32>,
    pub idf: Vec<f32>,
    pub navigation: bool,
    pub exact_title: bool,
}

fn unique_field(book: &Book, field: impl Fn(&crate::model::Record) -> String) -> String {
    book.origins
        .iter()
        .map(field)
        .filter(|s| !s.is_empty())
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect::<Vec<_>>()
        .join("\n")
}

// Counts only query terms; vocabulary and posting lists need not be materialized.
fn counts(text: &str, query: &[String]) -> (usize, Vec<usize>) {
    let mut length = 0;
    let mut counts = vec![0; query.len()];
    for token in terms(text) {
        length += 1;
        if let Some(i) = query.iter().position(|q| *q == token) {
            counts[i] += 1;
        }
    }
    (length, counts)
}

pub fn rank(books: &[Book], query: &[String]) -> Ranking {
    let fields: Vec<_> = books
        .iter()
        .map(|b| {
            let host = url::Url::parse(&b.url)
                .ok()
                .and_then(|u| u.host_str().map(str::to_owned))
                .unwrap_or_default();
            [
                unique_field(b, |r| r.title.clone()),
                format!("{host} {}", b.url),
                unique_field(b, |r| r.tags.join(" ")),
                unique_field(b, |r| r.folder.clone()),
                b.kind.clone(),
                unique_field(b, |r| r.excerpt.clone()),
                unique_field(b, |r| r.note.clone()),
            ]
            .map(|f| counts(&f, query))
        })
        .collect();
    let mut average = [0.; 7];
    let mut df = vec![0; query.len()];
    for fields in &fields {
        for (f, (len, _)) in fields.iter().enumerate() {
            average[f] += *len as f32;
        }
        for (q, count) in df.iter_mut().enumerate() {
            *count += usize::from(fields.iter().any(|(_, hits)| hits[q] > 0));
        }
    }
    for avg in &mut average {
        *avg = (*avg / books.len().max(1) as f32).max(1.);
    }
    let idf: Vec<_> = df
        .iter()
        .map(|&n| (1. + (books.len() as f32 - n as f32 + 0.5) / (n as f32 + 0.5)).ln())
        .collect();
    let weights = [6., 3., 3., 1.5, 1., 1., 1.5];
    let entity: Vec<_> = query
        .iter()
        .filter(|t| !["blog", "website", "homepage", "site", "home"].contains(&t.as_str()))
        .collect();
    let navigational = query.len() <= 5 && entity.len() >= 2 && entity.len() < query.len();
    let mut navigation = false;
    let mut exact_title = false;
    let scores = fields
        .iter()
        .zip(books)
        .map(|(fields, book)| {
            let mut score = 0.;
            for (q, term_idf) in idf.iter().enumerate() {
                let evidence: f32 = fields
                    .iter()
                    .enumerate()
                    .map(|(f, (len, hits))| {
                        let tf = hits[q] as f32;
                        weights[f] * 2.2 * tf
                            / (tf + 1.2 * (0.25 + 0.75 * *len as f32 / average[f]))
                    })
                    .sum();
                score += term_idf * evidence;
            }
            let title_terms = terms(&unique_field(book, |r| r.title.clone()));
            if !navigational
                && query.len() >= 2
                && book.origins.iter().any(|r| {
                    [
                        r.title.as_str(),
                        r.title.split([':', '|', '—']).next().unwrap_or(&r.title),
                    ]
                    .iter()
                    .any(|title| {
                        let mut title = terms(title);
                        title.sort();
                        title.dedup();
                        title == query
                    })
                })
            {
                exact_title = true;
                score += idf.iter().sum::<f32>() * 8.;
            }
            let title_complete = entity.iter().all(|t| title_terms.contains(t));
            let root = url::Url::parse(&book.url).is_ok_and(|u| {
                ["/", "/blog", "/blog/", "/blogs", "/blogs/"].contains(&u.path())
                    && u.query().is_none()
                    && u.fragment().is_none()
            });
            if navigational && title_complete && root && score > 0. {
                navigation = true;
                score += idf.iter().sum::<f32>() * 4.;
            }
            score
        })
        .collect();
    Ranking {
        scores,
        idf,
        navigation,
        exact_title,
    }
}

pub fn passage_score(text: &str, query: &[String], idf: &[f32]) -> f32 {
    let (length, hits) = counts(text, query);
    hits.iter()
        .zip(idf)
        .map(|(&tf, idf)| {
            idf * 2.2 * tf as f32 / (tf as f32 + 1.2 * (0.25 + 0.75 * length as f32 / 60.))
        })
        .sum()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{index, model::Record};
    #[test]
    fn duplicate_origins_do_not_multiply_field_votes() {
        let mut r = Record::new("manual", "fixture", "1", "https://example.org/a").unwrap();
        r.title = "SQLite ranking".into();
        let mut other = r.clone();
        other.provider = "raindrop".into();
        let a = index::merge(vec![r.clone()], &[], &[], None);
        let b = index::merge(vec![r, other], &[], &[], None);
        assert_eq!(
            rank(&a, &terms("SQLite ranking")).scores,
            rank(&b, &terms("SQLite ranking")).scores
        );
    }
    #[test]
    fn long_notes_cannot_outweigh_complete_title() {
        let mut a = Record::new("manual", "fixture", "1", "https://example.org/a").unwrap();
        a.title = "SQLite BM25 ranking".into();
        let mut b = Record::new("manual", "fixture", "2", "https://example.org/b").unwrap();
        b.note = "SQLite BM25 ranking ".repeat(100);
        let books = index::merge(vec![a, b], &[], &[], None);
        let scores = rank(&books, &terms("SQLite BM25 ranking")).scores;
        assert!(scores[0] > scores[1]);
        assert_eq!(passage_score("cartesian carpet", &terms("cat"), &[1.]), 0.);
    }
    #[test]
    fn subtitle_free_title_is_a_precise_lookup() {
        let mut r = Record::new("manual", "fixture", "1", "https://example.org/title").unwrap();
        r.title = "Database recovery: a practical guide".into();
        let books = index::merge(vec![r], &[], &[], None);
        assert!(rank(&books, &terms("database recovery")).exact_title);
        assert!(!rank(&books, &terms("database corruption")).exact_title);
    }
}
