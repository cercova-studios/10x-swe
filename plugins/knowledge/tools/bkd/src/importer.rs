use crate::{
    index::Book,
    model::{Record, clean, hash},
    state,
    store::Store,
};
use anyhow::{Result, ensure};
use serde::{Deserialize, Serialize};
use std::{
    collections::BTreeSet,
    io::{BufRead, Read, Write},
    path::Path,
};
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Candidate {
    pub url: String,
    pub title: String,
    pub kind: String,
    pub origins: Vec<Record>,
    pub status: String,
    pub evidence: serde_json::Value,
    pub selected: bool,
}
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Plan {
    pub schema: u8,
    pub destination: String,
    pub criteria: serde_json::Value,
    pub candidates: Vec<Candidate>,
}
impl Plan {
    pub fn id(&self) -> Result<String> {
        Ok(hash(serde_json::to_vec(self)?))
    }
    pub fn selected(&self) -> Result<Vec<Record>> {
        ensure!(
            self.schema == 1 && self.destination.len() == 64,
            "Invalid review plan"
        );
        let mut seen = BTreeSet::new();
        let mut out = Vec::new();
        for c in &self.candidates {
            ensure!(seen.insert(c.url.clone()), "Repeated review URL");
            if !c.selected {
                continue;
            }
            ensure!(
                c.status != "pruned",
                "Archived URL cannot be republished by import"
            );
            ensure!(!c.origins.is_empty(), "Missing review origin");
            for r in &c.origins {
                let mut r = r.remote();
                ensure!(r.url == c.url, "Review origin/URL mismatch");
                r.title = c.title.clone();
                r.kind = c.kind.clone();
                r.kind_source = "manual".into();
                r.validate()?;
                out.push(r);
            }
        }
        Ok(out)
    }
}
pub fn preview(
    books: Vec<Book>,
    criteria: serde_json::Value,
    store: &Store,
    evidence: serde_json::Value,
) -> Result<Plan> {
    let records = books
        .iter()
        .flat_map(|b| b.origins.clone())
        .collect::<Vec<_>>();
    let statuses = store.preview(&records)?;
    let candidates = books
        .into_iter()
        .map(|b| Candidate {
            status: statuses
                .get(&b.url)
                .cloned()
                .unwrap_or_else(|| "new".into()),
            evidence: evidence.get(&b.id).cloned().unwrap_or_else(
                || serde_json::json!({"method":"structural-filters","semantic_match":"unverified"}),
            ),
            url: b.url,
            title: b.title,
            kind: b.kind,
            origins: b.origins,
            selected: false,
        })
        .collect();
    Ok(Plan {
        schema: 1,
        destination: store.identity.clone(),
        criteria,
        candidates,
    })
}
pub fn review(plan: &mut Plan, input: &mut impl BufRead, output: &mut impl Write) -> Result<bool> {
    writeln!(
        output,
        "Public destination: rsnair.tech reading feed\nURLs and titles will be published. Notes and tags remain metadata.\nCriteria: {}\n{} unique candidate URLs",
        plan.criteria,
        plan.candidates.len()
    )?;
    for (i, c) in plan.candidates.iter_mut().enumerate() {
        writeln!(
            output,
            "\n{}. [{}] {}\n{}\nType: {} · origins: {}\nEvidence: {}",
            i + 1,
            c.status,
            clean(&c.title),
            c.url,
            c.kind,
            c.origins
                .iter()
                .map(|r| r.provider.as_str())
                .collect::<Vec<_>>()
                .join(", "),
            c.evidence
        )?;
        for origin in &c.origins {
            writeln!(
                output,
                "  {} / {} · type: {} ({}) · saved: {}\n  Tags: {}\n  Excerpt: {}\n  Notes: {}",
                clean(&origin.provider),
                clean(&origin.account),
                origin.kind,
                origin.kind_source,
                origin.saved_at.as_deref().unwrap_or("unknown"),
                clean(&origin.tags.join(", ")),
                clean(&origin.excerpt)
                    .chars()
                    .take(1000)
                    .collect::<String>(),
                clean(&origin.note).chars().take(600).collect::<String>()
            )?;
        }
        c.selected = false;
        if c.status == "pruned" {
            writeln!(
                output,
                "Skipped: archived by link cleanup. Restore separately."
            )?;
            continue;
        }
        loop {
            write!(output, "Include? [y/n/e=edit title/q=cancel] ")?;
            output.flush()?;
            let mut line = String::new();
            if input.read_line(&mut line)? == 0 {
                return Ok(false);
            }
            match line.trim() {
                "y" => {
                    c.selected = true;
                    break;
                }
                "n" => break,
                "q" => return Ok(false),
                "e" => {
                    write!(output, "Public title: ")?;
                    output.flush()?;
                    let mut title = String::new();
                    if input.read_line(&mut title)? == 0 {
                        return Ok(false);
                    }
                    ensure!(
                        crate::model::valid_text(title.trim(), 4096),
                        "Invalid title"
                    );
                    c.title = title.trim().into();
                }
                _ => writeln!(output, "Choose y, n, e or q.")?,
            }
        }
    }
    let selected: Vec<_> = plan.candidates.iter().filter(|c| c.selected).collect();
    if selected.is_empty() {
        writeln!(output, "Nothing selected; no writes.")?;
        return Ok(false);
    }
    writeln!(
        output,
        "\nFinal public selection ({} URLs):",
        selected.len()
    )?;
    for c in &selected {
        writeln!(output, "{} — {}", clean(&c.title), c.url)?;
    }
    let expected = format!("PUBLISH {}", selected.len());
    write!(
        output,
        "Type {expected} to confirm, or anything else to cancel: "
    )?;
    output.flush()?;
    let mut line = String::new();
    input.read_line(&mut line)?;
    Ok(line.trim() == expected)
}
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Pending {
    pub schema: u8,
    pub destination: String,
    pub operation: String,
    pub records: Vec<Record>,
}
#[derive(Debug)]
pub struct ImportFailure {
    pub message: String,
    pub progress: serde_json::Value,
}
impl std::fmt::Display for ImportFailure {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.message)
    }
}
impl std::error::Error for ImportFailure {}
fn partial(
    error: anyhow::Error,
    results: &[serde_json::Value],
    operation: &str,
    remaining: usize,
) -> anyhow::Error {
    ImportFailure{message:error.to_string(),progress:serde_json::json!({
        "complete":false,"public":true,"confirmed_batches":results,
        "uncertain_operation":operation,"remaining_origins":remaining,
        "recovery":"Run bkd retry --apply for the uncertain batch; reapply the SAME reviewed plan for the remaining batches. Receipts prevent repeated writes."
    })}.into()
}
pub fn operation(destination: &str, records: &[Record]) -> Result<String> {
    Ok(hash(serde_json::to_vec(&(destination, records))?))
}
pub fn apply(home: &Path, plan: &Plan, approve: &str, store: &Store) -> Result<serde_json::Value> {
    ensure!(
        plan.destination == store.identity && plan.id()? == approve,
        "Review approval/destination mismatch; nothing written"
    );
    let records = plan.selected()?;
    ensure!(!records.is_empty(), "No selected bookmarks");
    let results = apply_batches(home, &store.identity, &records, |batch, operation| {
        store.apply(batch, operation)
    })?;
    Ok(
        serde_json::json!({"applied":true,"public":true,"batches":results,"selected_urls":plan.candidates.iter().filter(|c|c.selected).count()}),
    )
}
fn apply_batches(
    home: &Path,
    destination: &str,
    records: &[Record],
    mut write: impl FnMut(&[Record], &str) -> Result<serde_json::Value>,
) -> Result<Vec<serde_json::Value>> {
    let pending = home.join("pending");
    state::prepare(&pending)?;
    let mut results = Vec::new();
    for (batch_number, batch) in records.chunks(100).enumerate() {
        let operation = operation(destination, batch)?;
        let file = pending.join(format!("{operation}.json"));
        let journal = state::write_json(
            &file,
            &Pending {
                schema: 1,
                destination: destination.into(),
                operation: operation.clone(),
                records: batch.to_vec(),
            },
        );
        if let Err(e) = journal {
            return Err(partial(
                e,
                &results,
                &operation,
                records.len() - batch_number * 100,
            ));
        }
        let result = write(batch, &operation)
            .map_err(|e| partial(e, &results, &operation, records.len() - batch_number * 100))?;
        results.push(result);
        std::fs::remove_file(file).map_err(|e| {
            partial(
                e.into(),
                &results,
                &operation,
                records.len() - (batch_number * 100 + batch.len()),
            )
        })?;
    }
    Ok(results)
}
pub fn import_relationships(
    mut reader: impl std::io::Read,
    store: Option<&Store>,
    apply: bool,
) -> Result<serde_json::Value> {
    let mut raw = Vec::new();
    std::io::Read::by_ref(&mut reader)
        .take(8 * 1024 * 1024 + 1)
        .read_to_end(&mut raw)?;
    ensure!(
        raw.len() <= 8 * 1024 * 1024,
        "Relationship artifact exceeds 8 MiB"
    );
    let mut value: serde_json::Value = serde_json::from_slice(&raw)?;
    if value["ok"] == true && value["schema"] == 1 {
        value = value["data"].take();
    }
    ensure!(
        value.as_object().is_some_and(|o| o.len() == 2) && value["schema"] == 1,
        "Invalid relationship artifact"
    );
    let rows: Vec<crate::graph::Relation> = serde_json::from_value(value["relationships"].clone())?;
    ensure!(
        rows.len() <= 10000,
        "Relationship artifact exceeds 10000 links"
    );
    let mut seen = BTreeSet::new();
    for r in &rows {
        r.validate()?;
        ensure!(
            seen.insert((&r.a, &r.b, &r.kind)),
            "Repeated relationship identity"
        );
    }
    if apply {
        let store =
            store.ok_or_else(|| anyhow::anyhow!("Relationship apply requires a destination"))?;
        for (completed, r) in rows.iter().enumerate() {
            if let Err(e) = store.write_relation(&r.a, &r.b, &r.kind, false, r.suppressed) {
                return Err(ImportFailure{message:e.to_string(),progress:serde_json::json!({"complete":false,"relationships_confirmed":completed,"recovery":"Reapply the same artifact; relationship setters are idempotent."})}.into());
            }
        }
    }
    Ok(
        serde_json::json!({"relationships":rows.len(),"applied":apply,"public":false,"next":"After apply, run bkd sync --source neon to refresh local relationships."}),
    )
}
pub fn retry(home: &Path, store: &Store) -> Result<usize> {
    let pending = home.join("pending");
    if !pending.exists() {
        return Ok(0);
    }
    ensure!(!pending.is_symlink(), "Invalid pending directory");
    let mut batches = Vec::new();
    for entry in std::fs::read_dir(pending)? {
        let path = entry?.path();
        if path.extension().is_none_or(|e| e != "json") {
            continue;
        }
        ensure!(
            !path.is_symlink() && path.metadata()?.len() <= 8 * 1024 * 1024,
            "Invalid pending journal"
        );
        let mut p: Pending = state::read_json(&path)?;
        ensure!(
            p.schema == 1
                && p.destination == store.identity
                && !p.records.is_empty()
                && p.records.len() <= 100,
            "Pending destination/batch mismatch"
        );
        for r in &mut p.records {
            r.validate()?;
        }
        ensure!(
            operation(&p.destination, &p.records)? == p.operation,
            "Pending checksum mismatch"
        );
        batches.push((path, p));
    }
    let n = batches.len();
    for (path, p) in batches {
        store.apply(&p.records, &p.operation)?;
        std::fs::remove_file(path)?;
    }
    Ok(n)
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn uncertain_second_batch_retains_journal_and_reports_first() {
        let tmp = tempfile::tempdir().unwrap();
        let records: Vec<_> = (0..101)
            .map(|i| {
                Record::new(
                    "raindrop",
                    "me",
                    &i.to_string(),
                    &format!("https://a.com/{i}"),
                )
                .unwrap()
            })
            .collect();
        let mut calls = 0;
        let e = apply_batches(tmp.path(), &"a".repeat(64), &records, |_, _| {
            calls += 1;
            if calls == 1 {
                Ok(serde_json::json!({"new":100}))
            } else {
                anyhow::bail!("Lost confirmation")
            }
        })
        .unwrap_err();
        let failure = e.downcast_ref::<ImportFailure>().unwrap();
        assert_eq!(failure.progress["confirmed_batches"][0]["new"], 100);
        let files: Vec<_> = std::fs::read_dir(tmp.path().join("pending"))
            .unwrap()
            .collect();
        assert_eq!(files.len(), 1);
        let pending: Pending = state::read_json(&files[0].as_ref().unwrap().path()).unwrap();
        assert_eq!(pending.records.len(), 1);
    }
    fn plan() -> Plan {
        let r = Record::new("raindrop", "me", "1", "https://openai.com/index/research/").unwrap();
        Plan {
            schema: 1,
            destination: "a".repeat(64),
            criteria: serde_json::json!({"domain":"openai.com"}),
            candidates: vec![Candidate {
                url: r.url.clone(),
                title: "Research".into(),
                kind: "article".into(),
                origins: vec![r],
                status: "new".into(),
                evidence: serde_json::json!({}),
                selected: false,
            }],
        }
    }
    #[test]
    fn no_default_or_eof_approval() {
        let mut p = plan();
        assert!(!review(&mut p, &mut std::io::Cursor::new(b"y\n"), &mut Vec::new()).unwrap());
        assert!(
            !review(
                &mut plan(),
                &mut std::io::Cursor::new(b"n\n"),
                &mut Vec::new()
            )
            .unwrap()
        );
    }
    #[test]
    fn deliberate_confirmation_bound_to_selection() {
        let mut p = plan();
        let old = p.id().unwrap();
        assert!(
            review(
                &mut p,
                &mut std::io::Cursor::new(b"y\nPUBLISH 1\n"),
                &mut Vec::new()
            )
            .unwrap()
        );
        assert_ne!(old, p.id().unwrap());
        assert_eq!(p.selected().unwrap().len(), 1);
        p.candidates[0].url = "https://evil.org".into();
        assert!(p.selected().is_err());
    }
    #[test]
    fn pruned_never_selected() {
        let mut p = plan();
        p.candidates[0].status = "pruned".into();
        p.candidates[0].selected = true;
        assert!(p.selected().is_err());
    }
}
