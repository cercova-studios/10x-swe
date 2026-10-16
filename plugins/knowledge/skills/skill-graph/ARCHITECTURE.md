# Local skill graph contract

Existing plain reference-topic entries in top-level `references` remain metadata. Only quoted Wikilinks become graph relationships. Portable export preserves those ordinary entries beside graph links.

A local CLI reads explicit registered skill roots and YAML frontmatter. It never executes skill code, installs dependencies, fetches content or grants permissions. Use an isolated runtime with PyYAML 6.0.3 for frontmatter and orjson 3.11.3 for JSON. orjson reads bytes and produces bytes; the CLI decodes output as UTF-8 for display and text files.

## Data and identity
Roots have stable scope IDs and absolute paths. Default identity is scope plus relative skill folder, preserving same-name versions. Optional skill-graph-id overrides identity. Metadata values are strings: skill-graph-uses is a comma-separated list of scoped IDs; skill-graph-used-by is a generated mirror of incoming edges. Outgoing declarations are authoritative. Backlinks and graph.json/INDEX.md are derived.

All real skill folders are indexed. Symlink aliases retain their lexical paths but resolve to one canonical node; different folder contents remain separate. Symlinks in skill contents are not executed. Broken aliases, YAML errors, duplicate IDs, unresolved targets and stale backlinks fail check visibly. Body links and legacy related-skills are candidate hints, never authoritative dependencies. Cycles are permitted and queries traverse one hop by default.

## Commands and boundaries
Build writes graph.json and INDEX.md only to the selected output directory. The Rust `skill-search` tool owns SQLite FTS5 discovery and remote quarantine/scanner/loading; its reviewed source is in scripts/search-core. Python's redundant literal search command has been removed. Python neighbors retains one-hop maintenance diagnostics; the Rust command is the agent discovery interface. Both validate current inventory, additions and removals. Session-catalog selection remains the fallback for paraphrases. Audit computes full-tree fingerprints including file modes and reports duplicate candidates. Annotate stages frontmatter preserving body bytes and metadata; it never changes active roots. Promotion requires operation-specific review evidence and concurrent-change checks: scanner acceptance for direct registry installs, construction review for local revisions. The Rust remote load/install commands retain their stricter receipt gate; local authoring uses staged filesystem promotion, not a bypass flag. See references/remote-loading.md for the explicit new-folder installer and its rejection boundaries.

## Lifecycle
Optional Rust classification uses pinned Jev independent fit judgments over global id/name/description only, behind explicit cloud consent and a supplied threshold. It excludes project metadata, paths and skill bodies; no classification grants acceptance or executes content. Requests, responses and exact-payload caches are bounded; current usage excludes cache hits. Offline search remains the default.

Before direct registry installation or update, agents review upstream content for clarity, concision and full-bundle overlap and scan the exact final artifact. Locally authored or substantively remixed skills instead require construction review of all retained resources, capability boundaries, validation, and provenance/licenses. Cosmetic rewrites remain direct installs. Neither editorial nor construction review is certified by the scanner or classifier; changed bytes cannot inherit an old receipt.

Global instructions direct agents to bounded neighbor discovery. Selecting a graph node does not authorize use, delegation, egress or spending; existing rules apply. Project-root registration is explicit and local, not a filesystem crawler. Backups preserve exact prior folders or frontmatter for rollback. Rebuild indexes after approved updates, installation, removal or root changes; file hashes expose staleness without starting a resident watcher.

Search is offline by default. `search QUERY --remote` adds skills.sh metadata alongside local results, retaining separate local/remote origins. The old --scope flag is removed. --remote conflicts with --only-global.

Registry security enrichment: --remote search queries the documented www.skills.sh audit endpoint for returned public skill identities, without credentials. Whitelist provider/verdict/summary/date/risk/report URL; reject mismatched identities and malformed metadata. At most16providers and128KiB per response; all result audits share a10second network deadline. Missing/errors report unavailable, never pass. Registry dates and exact-content binding limitations remain visible. Search caches expire after60seconds with versioned adapter keys. Registry verdicts cannot grant exact-bundle acceptance.

## Unified relationships and planning
Top-level quoted scoped Wikilink lists encode uses, generated used-by, related and references; matching body links carry use context without repeated guidance. Inferred export links are labeled related-inferred. Legacy string metadata remains readable for unchanged bundles; mixed declarations must agree. The derived graph adds observed references and locally inferred related links, cluster membership and bridge scores in graph.json. Map records bind entrypoint hashes, chunk locators, model and extraction version. Unchanged rebuilds retain mapping; changed inventory marks it stale. Rust reads typed links, constructs bounded candidate routes, and renders cluster islands; only uses remain workflow dependencies. Agents verify applicability and capability coverage before ordering execution. Neither similarity nor community membership grants acceptance. Map uses the installed source-insights BGE runtime explicitly; ordinary search has no model process. Obsidian export writes a fresh separate Markdown vault and leaves active skill files unchanged.

`skill-search refresh` explicitly rebuilds inventory through the installed graph helper, validates it, rebuilds the local semantic map with existing bounded mapping machinery, and transactionally refreshes SQLite from the final checked graph. `--graph` selects a graph.json with sibling roots.json. No active skills change. Failure exits nonzero and may leave completed earlier index stages published; a mapping failure does not update the catalog.

## Portable discovery export

`skill-search export` emits one complete `knowledge-snapshot/v2` JSONL record with typed skill/workflow nodes, revisions and labeled relationships. `--query 'TASK' --limit 5` adds independently ranked lexical hits. Inventory is checked before and after export. Paths and handoff commands are discovery metadata, never authority. Export invokes no consumer and does not load skill instructions. Consumers can combine this record with another producer's record through a pipe without reading private graph/catalog formats.

## Workflow layer
Owned workflows/*.md documents with workflow/v1 metadata become kind=workflow
nodes beside skills. Identity is owner ID + /workflows/ + document stem.
metadata.skill-graph-workflows declares associations. associated_workflow and
uses_skill edges remain separate from dependency/backlink uses edges. Participants
must resolve to skills. Runner/resources are bundle-relative, retained and hash
checked; escapes/symlinks and stale resources fail. Owner aliases mirror workflows.
Annotation skips workflow documents. Search and terminal graph expose the layer;
load returns the document without executing resources. Derived catalog schema 3
rebuilds from the checked graph. Export is knowledge-snapshot/v2, corpus skills,
with skill:/workflow: IDs, closed edges, lexical hits and revisions. Workflow
revisions hash document/resource hashes. bkd retains v1 reading for saved packets.
Discovery grants no permission; inventory/search have no Dagu dependency.

Markdown vault export writes workflow documents as WORKFLOW.md and preserves
typed Wikilinks to participants and associations. It exports notes only; runner
YAML and scripts remain in the installed owner bundle. The vault is a reader
artifact, not a runnable workflow installation.

## Portable distribution profile
AGENT_KNOWLEDGE_HOME selects installation resources and state. `refresh --lexical`
rebuilds declared inventory and FTS5 without running mapping or a model. The graph
TUI falls back to connected components when no semantic map exists. Model invocation
is a stateless local_embeddings primitive, independent of source-insights storage.
Read-only external roots use namespaced identities and retain original IDs, trust
and unresolved references in exports/loads. They never receive generated rewrites.
Links outside their import namespace remain unresolved; review them explicitly rather
than changing owned backlink authority through an unreviewed external declaration.
