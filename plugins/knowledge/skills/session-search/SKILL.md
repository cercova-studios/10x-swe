---
name: session-search
description: Recall public session turns with exact provenance, bounded excerpts and
  independent piped exports.
metadata:
  skill-graph-id: global/session-search
  skill-graph-workflows: global/source-insights/workflows/session-to-insight
  skill-graph-uses: ''
  skill-graph-used-by: ''
---

# Recall prior work

Run `session-search status` to inspect owned index state. A new setup has an empty
index; explicitly index a selected harness when needed. Bootstrap never crawls source
sessions. Verify actual options with `session-search --help`.

The CLI is a standalone Rust executable. `SESSION_SEARCH_DB` selects the existing
SQLite index; the native default remains `~/.local/share/session-search/index.db`.
Owned installations select their own `state/session-search.sqlite` without Python.
Queries never create or upgrade an index. Explicit indexing retains existing data
when an adapter or enrichment fails.

`session-search export --mode naive --agent codex --role assistant --limit 1 'topic'`
emits bounded knowledge-snapshot/v1 JSONL. Stage producer output successfully before
starting consumers. Only Codex and Claude currently support exact exported turn
citations. Other adapter results are discovery until inspected. Hidden reasoning is
excluded. Hash-embedding similarity is a heuristic, not neural semantic retrieval.

Exports retain native IDs, source paths, JSONL line/pointer, role, record hashes and
coverage/redaction limits. Inspect selected excerpts before sharing. Recorded
assistant proposals are not independently observed facts. Select user for requirements
or tool for reported outcomes; omit the role filter to retain all public roles.

An optional independent consumer accepts
`source-insights prepare-session session:codex:EXACT_ID --records FILE --work NEW_DIR`.
The associated [session-to-insight workflow](../source-insights/workflows/session-to-insight.md)
adds an explicit review gate. The producer never depends on the consumer or runner.
Read `ARCHITECTURE.md` for adapter and provenance limits.

## Local neural embeddings

Build with `cargo build --locked --release --features neural` from
`plugins/knowledge/tools/session-search`. Set `SESSION_SEARCH_EMBEDDER=fastembed`,
`ORT_DYLIB_PATH` to an installed ONNX Runtime library, and
`SESSION_SEARCH_MODEL_DIR` to an existing BGE-small-en-v1.5 bundle containing
`model.onnx`, `tokenizer.json`, `config.json`, `special_tokens_map.json` and
`tokenizer_config.json`. The CLI loads these local files.

Use `session-search index --enrich-only` to rebuild an existing index's vectors.
Semantic search checks that the configured model matches the indexed model;
a failed rebuild retains the previous vectors. The portable build uses hash
embeddings by default.
