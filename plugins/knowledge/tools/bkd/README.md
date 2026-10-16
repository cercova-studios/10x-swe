# BookmarkDrop

`bookmarkdrop` / `bkd` is a Rust CLI for local bookmark retrieval, relationship maps, and deliberately reviewed publishing to Neon and rsnair.tech. Bare `bkd` opens a minimalist Ratatui capture screen. `bkd ui` opens a Finder-style bookmark viewer with link drops, Quick Look and reader mode. Use explicit subcommands with `--json` for agents or `search --rich` for terminal Markdown.

## Build

```sh
cargo build --release --locked
cargo test --locked
cargo clippy --locked --all-targets -- -D warnings
```

Both binaries are in `target/release/`. This release targets macOS. BookmarkDrop never calls source-insights or skill-search and has no Python dependency. Knowledge is explicit caller-supplied JSONL. Bookmark BGE inference uses the installed local runtime on demand.

## Connect

```sh
bkd auth instapaper --account my-account
bkd auth raindrop --account my-account
bkd auth neon --account my-database
```

Enter credentials at the hidden prompt or pipe them on stdin. Credentials stay in the OS credential store, bound to the cache directory and account. Each cache holds one account per provider. Optional explicit environment variables are `BKD_INSTAPAPER_TOKEN`, `BKD_RAINDROP_TOKEN`, and `BKD_DATABASE_URL`. Tokens are OAuth bearer tokens. Neon needs a PostgreSQL connection URL for the restricted publisher role.

The Neon administrator must review and activate [database/bookmarkdrop.sql](database/bookmarkdrop.sql) before Neon sync, previews or saves work. It creates restricted functions and a publisher role; it does not provision or rotate passwords. For another database, run the migration first on an isolated branch. [Rollback](database/disable-publisher.sql) disables the publisher and revokes function execution; receipts and published links are retained. An already-running transaction may still finish.

Inject BKD_INSTAPAPER_TOKEN, BKD_RAINDROP_TOKEN and BKD_DATABASE_URL explicitly
for the selected connectors. Never put credentials in plans, exports or source files.
Persistent keychain auth is macOS-only; other platforms use injected environment
credentials. No connector or database is configured by the portable bootstrap.

## Search and graph

```sh
bkd sync --source instapaper,raindrop,neon
bkd sync --offline
bkd search "research on interpreting neural network features"
bkd search "chip huyen blog"
bkd search "research notes" --list
bkd search "machine learning" --kind blog --list
bkd search "transformer interpretability" --kind paper --source raindrop --json
bkd search "research notes" --rich
bkd graph
bkd graph --similarity
bkd graph --source raindrop --kind article --json
bkd related BOOKMARK_ID --json
bkd path BOOKMARK_ID OTHER_ID --json
bkd
```

`sync` refreshes full source snapshots and builds missing local vectors in one workflow. Unchanged content reuses cached vectors; identical text is embedded once. A failed scan preserves that source's previous records. An embedding failure preserves the previous complete generation. `sync --offline` builds missing vectors from cached data without credentials or connector calls; it cannot be combined with `--source` or `--lexical-only`. `sync --lexical-only` refreshes without embeddings. Search combines lexical and local semantic rankings with bounded graph support. Use `--no-graph` to compare direct retrieval. Similarity and relevance scores are uncalibrated ranking signals.

Ranking uses whole-token, field-weighted BM25 and local BGE embeddings. Homepage requests with matching identity terms and exact/subtitle-free title queries skip model inference. Single-word lookup is literal. Other queries combine document and cached passage similarity without double voting. These heuristics and similarity cutoffs are provisional; no-match results can still miss relevant paraphrases.

`sync --offline` also builds missing passage vectors from existing excerpts and notes. JSON hits expose `passage` with verbatim text, source origin, field, byte offsets and field hash; top-level `strategy` identifies the retrieval route, and `passage_index` is `complete`, `partial` or `not-used`. A partial old cache remains searchable; offline sync completes passage coverage. No page fetching or external provider is involved. See [retrieval checks](docs/retrieval.md) for the benchmark and limits.

Search prints only the top bookmark URL by default. `--list` shows ranked rows, `--rich` opts into a rich ranked list, and `--json` retains complete structured results for agents. No matching bookmark exits with an error. `--limit` bounds list/JSON results without changing the one-URL default. URL-only mode skips external knowledge retrieval because corpus ranks do not change bookmark ranking.

Seven exclusive kinds: `blog` (blog home or post), `article` (other editorial articles), `video`, `paper`, `documentation`, `book`, `other`. Kind provenance accompanies records. Blog detection uses URL structure and known blog hosts; uncertain links stay `other`. Existing automatic classifications refresh when cached records are read, without reembedding or modifying stored user classifications. “Research blog post” is a semantic review criterion within `blog`.

The default graph includes recorded tags, collections, mentions and authored relationships. `--similarity` adds slower whole-library inferred similarity suggestions. Search uses bounded, query-gated recorded relationships; inferred similarity does not add another ranking vote. The former `--no-similarity` flag was removed; use plain `graph` for recorded relationships.

The fullscreen graph pages to fit the terminal. `j/k` selects, `n/p` pages, `/` filters labels, arrows pan, `+/-` or the mouse wheel zooms, `s` opens the list, `d` opens details, PageUp/PageDown scrolls details, Escape closes overlays, and `q` or Ctrl+C exits. Green edges are recorded/user relationships; gray edges are inferred similarity. Visual proximity is only layout. JSON and the browser's node list expose full edge evidence, including relationships crossing display pages.

## Knowledge records

Producers own extraction, retrieval and revision checks. BookmarkDrop consumes only
explicit `knowledge-snapshot/v1` JSONL records (skills/workflows use v2) through `--records FILE|-`.
It never reads another tool's library, graph, entrypoint or catalog, and never
starts another knowledge tool. No record grants execution or publication approval.

```sh
# Stage both successful producer records before starting the consumer.
set -euo pipefail
python3 ~/.agents/skills/source-insights/scripts/sources.py export \
  --query "skill discovery" > knowledge.jsonl.part
skill-search export --query "skill discovery" >> knowledge.jsonl.part
mv knowledge.jsonl.part knowledge.jsonl
cat knowledge.jsonl | bkd --records - search "skill discovery" --json
bkd --records knowledge.jsonl graph
bkd --records knowledge.jsonl ui
bkd --records knowledge.jsonl inspect BOOKMARK_ID --json
bkd --records knowledge.jsonl path BOOKMARK_ID skill:global/skill-graph --json
bkd --records knowledge.jsonl link-knowledge skill:global/skill-graph insight:ENTRY:1 \
  --reviewed --reason "Reviewed the claim and its applicability"
```

Use a fresh destination file. Export without `--query` for full graph navigation;
queried exports also include complete navigation metadata. For interactive TUI,
graph or browser use a file; stdin is for data-oriented commands. `--records` does
not change the default top-bookmark URL result; request `--json`, `--list` or
`--rich` for combined search. [The external recipe](examples/compose-search.zsh)
stages records and prevents either producer failure from reaching the consumer.

Incoming ranks apply only to the exact producer query. New queries search supplied
labels and descriptive metadata locally and report `snapshot lexical`; they do not
pretend to be a fresh hybrid provider search. Re-export to refresh producer ranks.
Each corpus keeps its own ordering. Source/domain/kind filters affect bookmarks,
not insights, skills or sessions. Exact source/request URLs join bookmarks to inspected
versions; citations, coverage and caveats remain producer-owned data.

Session-search can independently export a third `sessions` corpus. Supply its
packet alongside insights and skills to search session evidence and navigate
recorded turn membership. Published source-insights entries retain exact session/
turn revision pins; matching supplied turns produce `captured_from` graph edges.
No session URL mention becomes a bookmark link, and no companion tool is invoked.
See [the record contract](docs/knowledge-integration.md) for the piped recipe,
coverage bounds and changed-pin behavior.

Reviewed links stay in private `knowledge-links.json`, pin supplied endpoint
revisions, and become stale when a new snapshot changes those revisions. Remove
with `link-knowledge A B --remove`. BookmarkDrop cannot verify that an exported
snapshot is current; it makes no live freshness or independent review claim.
Only the producer validates its original files. Paths and handoff argument arrays
are displayed metadata, never opened or executed by the knowledge consumer.

See [the record contract and checks](docs/knowledge-integration.md) and
[the composable workflow](docs/workflow.md). The former implicit bridge and its
configuration flags have been removed rather than retained as aliases.

## Your OpenAI import example

After source sync and Neon setup:

```sh
bkd import --source instapaper,raindrop --domain openai.com \
  --kind blog --query "research blog posts"
```

The domain filter includes `openai.com` and its subdomains, never lookalike suffixes. Source/type/domain filters are deterministic. The query attaches local ranking evidence. Every structurally eligible URL is shown, including candidates the model did not rank, so semantic uncertainty cannot silently drop a bookmark.

The wizard shows each URL, title, type, contributing origins, relevance evidence, and existing/new/pruned status. Choose y/n for each URL, optionally edit its public title, then review the final list and type `PUBLISH N`. Nothing is preselected. EOF or cancellation writes nothing. Only URLs and titles join the public feed; notes, tags and origin metadata stay outside its projection.

For agents, use a portable review plan:

```sh
bkd import --source instapaper,raindrop --domain openai.com \
  --kind blog --query "research blog posts" \
  --dry-run --plan ./openai-review.json --json
bkd import --plan ./openai-review.json --select BOOKMARK_ID,OTHER_ID --dry-run --json
bkd import --plan ./openai-review.json --apply --approve PLAN_ID --json
```

Read the complete preview before selecting. Candidate IDs are SHA256 of the exact URL. The second command returns the checksum of the **selected** plan. Approval binds those URLs, titles, origins and criteria to the destination database identity. Editing the plan invalidates the approval checksum. There is no unattended “yes to everything” switch.

Imports deduplicate exact URLs across sources, retain each origin, preserve existing public titles, and block archived URLs. Publishing uses batches of at most 100 origins; the entire import is not one transaction. A partial failure reports confirmed batches and leaves an uncertain destination-bound journal. Run `bkd retry --apply`, then reapply the same approved plan for remaining batches; remote receipts prevent repeated writes. A tombstone created after preview can still block publication at commit.

## Save, export, restore

```sh
bkd save https://example.org/article --title "Reviewed public title" --kind article
bkd export --source instapaper,raindrop > bookmarks.jsonl
bkd import bookmarks.jsonl
bkd export --relationships --json > relationships.json
bkd import relationships.json --relationships --dry-run --json
bkd import relationships.json --relationships --apply --json
```

Bookmark export is origin-preserving JSONL, even with `--json`. Relationship artifacts contain authored links and suppressions; restoring them does not publish bookmark URLs. Sync Neon afterward to refresh local relationships.

`bkd ui` opens a minimalist file-browser view: source sidebar, name-sorted bookmark rows, type filters, local search and 100-row pages. Drop a browser link anywhere in the window, paste a URL outside a text field, or use + to open capture. Nothing saves until you review the URL/title/type and check public publication. Editing clears that confirmation. This retains existing receipts, title preservation and tombstone protection.

Select a row and press Space (or double-click) for Quick Look. The web view uses a sandboxed iframe with no referrer. Sites can block embedding; Open original remains available. Aa explicitly fetches public HTML and converts it to an ephemeral text reader. It removes scripts, images, forms and navigation and never inserts fetched HTML into the live document. Saved notes and citations remain in the adjacent notes view. Escape closes Quick Look and stops its frame; conversion never changes bookmark records or publishes anything.

Reader mode supports public UTF-8 HTML, up to 2 MiB, five checked redirects and a 20-second HTTP budget. It rejects private/reserved destinations and custom ports, pins validated DNS addresses and sends no browser cookies or credentials. OS DNS resolution may take longer than the HTTP budget; the foreground server handles requests sequentially. This basic text extractor cannot render JavaScript-only pages, bypass logins, or convert PDFs. It may omit article-adjacent content; use the original for a full source review.

The viewer runs only on 127.0.0.1 with a single-use launch link, session cookie, Host/Origin checks and local assets. Cached Markdown remains inert. [DESIGN.md](DESIGN.md) records the viewer conventions. No new UI framework or resident service is installed.

## Local state and inference

State defaults to `~/.local/share/bookmarkdrop`; override with `--home` or `BKD_HOME`. `doctor` reports local coverage, generation and pending writes without reading credentials. The SQLite cache is disposable; remote receipts and annotations remain in Neon.

`bkd model` prints the model path, SHA256 and runtime. Set `BKD_MODEL_PATH` to the already-downloaded BGE-small GGUF. The pinned hash is `c5d2302edc429f679642433b9f96dd217799727a06e675abef3b40a79f5e1589`. The model is verified before use, runs CPU-only and offline, and has no resident process. UTF-8 windows bound inputs; exact cosine retrieval uses cached vectors. Winnow-12B is not enabled or auto-started.

See [ARCHITECTURE.md](ARCHITECTURE.md) for boundaries and [verification](docs/verification.md) for evidence and unverified behavior.

## Terminal capture and review

Run `bkd` to open a quiet capture canvas, with no library rows on startup (or `bkd --lexical-only` without embeddings). Paste one HTTP(S) URL (or drop it in an emulator that delivers URL text) to open an editable draft. `a` starts manual capture; Tab changes URL/title/type fields and left/right cycles type. Enter requests a Neon duplicate/tombstone preview. Space selects individual bookmarks; `e` edits title/type, `p` opens the final public selection, and typing `PUBLISH N` confirms. Escape cancels; dropping or pasting text never publishes. Existing public titles and tombstones remain authoritative.

`/` searches, `f` edits source/type/domain filters, Enter opens styled Markdown and evidence details, `g` opens the graph, and `o` opens a validated bookmark URL. PageUp/PageDown scrolls long panels. `r` reviews every structurally eligible bookmark under the filters, with semantic results shown only as review evidence. `bkd --plan ./review.json` reviews an existing agent plan with nothing preselected. Agent commands remain noninteractive; `--json` is rejected in TUI mode.

After confirmed receipts, the TUI refreshes Neon without embeddings. Cache or search refresh failures do not undo a confirmed remote write; follow the displayed recovery command. Run `bkd sync --offline` when you want vectors for newly saved records. The user confirmed that Safari drag sends no input in installed WezTerm 20240203 on macOS. Its native drop handler accepts file paths, not Safari URL payloads. Copy and paste the URL instead; `?` shows keys and this limitation. The HTML viewer is retained alongside the TUI for browser capture and reading.

## Pipe portable bookmarks

```sh
bkd export --source instapaper,raindrop | bkd --home ./review-cache index - --lexical-only --json
bkd export --source raindrop | bkd import - --dry-run --plan ./review.json --json
```

Stdin is validated before changing the destination cache. A file-backed plan and explicit approval remain required for noninteractive publication. See [the Unix composition audit](docs/unix-composition.md) and the external `examples/compose-search.zsh` demonstration. The existing combined-search subprocess bridge remains pending replacement with explicit streams.
