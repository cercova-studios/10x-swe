---
name: skill-graph
description: Discover skills and workflows through independent lexical search, relationship
  paths and a terminal graph.
metadata:
  skill-graph-id: global/skill-graph
  skill-graph-uses: ''
  skill-graph-used-by: plugin/10x-swe/turnstile-spin
---

# Discover useful routes

Run `skill-search search 'task' --limit 5`, inspect selected entrypoints with `load
EXACT_ID`, then use `neighbors`, `path 'task'`, `related` or `graph`. Choose the
smallest applicable set. Relationships never grant execution, delegation or approval.

The packaged profile is offline keyword search. After inventory changes, run
`skill-search refresh --lexical`; every discovery/export checks freshness. Neural `map` and
`path --semantic` require a separately configured pinned BGE model and
`llama-embedding`. Missing models fail visibly; the declared graph remains usable.

`skill-search export --query 'task' --limit 5` emits knowledge-snapshot/v2 JSONL
with typed skills/workflows, resource revisions, labeled edges and independent ranks.

`knowledge-intake --root harness=/absolute/skills` inspects existing bundles as data.
Review the report before adding `--index`: this registers read-only, namespaced,
unreviewed nodes without rewriting or activating sources. Conflicts and unresolved
links remain visible. Indexing never creates scanner acceptance.

Read `references/maintenance.md` before editing registered skills. Stage local
changes, preserve licenses/provenance, apply construction review, generate backlinks,
and verify the graph before promotion. Direct remote registry installs require exact
final bundle acceptance: read `references/remote-loading.md`. Historical receipts
cannot bless changed bytes. Resolve paths from AGENT_KNOWLEDGE_HOME.
