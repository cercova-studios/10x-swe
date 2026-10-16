# BookmarkDrop architecture

## Domain and entrypoints

`src/model.rs` defines validated portable records and seven exclusive kinds. An origin is (provider, account, external_id). A bookmark ID is SHA256 of the exact validated URL, including query and fragment. `imported_origin` preserves the original identity through a Neon read/export/reimport cycle. Kinds are blog, article, video, paper, documentation, book and other. Recognizable blog URLs refresh automatic URL/provider-article classifications on read; manual choices and specific provider kinds remain unchanged. Classification does not change embedding bodies or persisted cache bytes. New kinds cannot overlap; uncertain URL detection stays other.

`src/lib.rs` owns CLI argument parsing and operation composition. Both binaries call the same entrypoint. Search prints the best bookmark URL by default; --list and --rich explicitly request ranked output. No bookmark match fails visibly. Combined knowledge retrieval runs only for list/rich/JSON output because external corpus ranks do not alter the top bookmark. JSON envelopes expose success/failure and partial-import progress. Origin exports are JSONL. `index -` and `import -` accept portable records on stdin; malformed input is fully rejected before cache publication. Piped records are data and cannot satisfy human approval. `tui.rs` and `ui.rs` consume the same retrieval/graph primitives.

## Reading, caching and retrieval

`connectors.rs` implements read-only Instapaper v2 bearer HTTP and Raindrop readers with a shared bounded HTTP transport: fixed HTTPS origins, no redirects, 30-second timeout, 8 MiB page limit, bounded rate-limit retries and pagination. A full source snapshot replaces records only after all pages succeed. `store.rs` reads Neon records and authored relationships in one repeatable-read transaction. Offset APIs cannot guarantee a frozen upstream collection during concurrent remote edits.

`state.rs` owns private local SQLite state, atomic JSON files and OS credentials. Each cache supports one account per provider. Credentials are bound to the canonical state directory and account. No native-app or importer credential discovery/reuse occurs.

`index.rs` computes missing vectors before acquiring the write transaction. Publication compares the revision captured before network reads, then atomically updates source records, coverage, vectors, Neon relationships and revision. A stale refresh or embedding error retains the previous complete generation. Read transactions keep graph/search records, vectors and generation consistent.

`sync` is the single refresh-and-index workflow. It fetches selected complete snapshots and indexes missing content across the resulting cache. `sync --offline` indexes cached data without connector calls; it conflicts with source selection and lexical-only mode. `sync --lexical-only` deliberately skips vectors. The separate cached-index command was removed; error guidance points to sync. Content hashes and the embedding recipe reuse unchanged vectors and deduplicate identical texts before inference.

`embedding.rs` verifies the exact pinned BGE-small F16 GGUF hash and invokes installed llama-embedding with CPU-only/offline settings. Up to eight 400-byte UTF-8 windows run per subprocess, reducing repeated model startup while retaining bounded input and runtime token batches; vectors are averaged and L2-normalized. Each subprocess has a 120-second deadline. No model process remains resident. Recipe changes require a cache-spec bump.

`search.rs` filters source origins before URL merging. `lexical.rs` scores whole tokens using weighted per-field BM25 (title 6, URL/domain 3, tags 3, collection 1.5, kind 1, excerpt 1, note 1.5); each field saturates independently. Corpus frequencies and lengths use only filtered books; duplicate field values across origins count once. Only query-term counts are retained, avoiding a materialized vocabulary or another derived database. Eligible metadata is still scanned per query; larger-library performance is unverified.

Confident homepage/blog-index requests require at least two identity terms present in selected titles. Exact title or subtitle-free title requests (colon, vertical bar, em dash) receive explicit preference. These precise routes skip embeddings and graph expansion; single-term lookup is literal and also skips embedding inference. Other queries fuse lexical and local cosine ranks. Semantic scores use the maximum of document and passage similarity, never two independent semantic votes. Pure semantic queries require provisional cosine 0.60; queries with lexical anchors use 0.45. These gates can miss relevant paraphrases and are not calibrated confidence probabilities. JSON reports navigation/exact-title/lexical/hybrid strategy.

`passage.rs` partitions cached excerpts and notes into nonoverlapping, word-boundary-preferred UTF-8 spans of at most 400 bytes. Evidence retains provider/account/external_id, field, exact byte offsets, verbatim text and full-field SHA256. Sync adds missing passage vectors through the existing content-addressed vector table and unchanged embedding recipe; originals and old document vectors remain valid. Old caches retain whole-document semantic retrieval and lexical passage evidence; JSON marks passage_index partial until sync --offline completes it. Search never indexes or calls connectors. Complete and not-used are the other coverage states. This retrieves cached annotations, not fetched full pages or papers.

Graph assistance builds adjacency once over recorded/authored edges. At most 20 direct seeds propagate strongest-path support through at most two bookmark hops/four stored edges, with an overall 5,000-edge work budget. Tag/collection hubs and high-degree nodes dilute support; second hops decay. Each intermediate and destination bookmark needs whole-token evidence or cosine at least 0.45. Mentions remain directed, cycles are excluded, and retained paths expose original edge evidence. Maximum support stays within 15% of one seed score; multiple paths cannot accumulate authority. Inferred similarity does not cast another graph vote. Precise lookups bypass graph work entirely.

`graph.rs` scans note/excerpt URL candidates once and resolves exact saved URLs, preserving first-match offsets and delimiter boundaries. It derives provider/account-scoped tag and collection hubs, exact-URL mentions with both boundaries checked, authored links and mutual-six-neighbor similarity suggestions at provisional cosine 0.78. Edges retain evidence and inferred/recorded/user status. Paths cap six stored edges and 5,000 work steps; neighborhoods cap 2,000 steps. The graph CLI defaults to recorded/authored relationships; --similarity explicitly adds slower inferred suggestions. Search assistance uses the separately bounded recorded-edge traversal above. Display paging never removes graph records. Metadata/vector loading currently materializes the bounded library in memory; whole-library RSS at production scale is unverified.

Similarity neighbor rows use at most eight temporary scoped workers, bounded by available cores and one worker per 128 records. Each row preserves ascending candidate order, scalar float accumulation, stable score ties and the six-neighbor cutoff. Worker creation errors propagate through the normal CLI error envelope. Workers finish before rendering; no resident process, derived cache, approximate edges or new dependency is introduced. Total similarity CPU work remains quadratic; wall time benefits from parallel cores.

## Explicit knowledge records

`knowledge.rs` validates bounded `knowledge-snapshot/v1` JSONL supplied through `--records FILE|-`. `lib.rs` reads it once; CLI, browser and terminal consume the immutable configuration. BookmarkDrop does not read companion libraries, graphs, entrypoint files or invoke their processes. Each producer owns export, citation/hash verification, inventory freshness and optional ranking. See docs/knowledge-integration.md for exact fields and bounds.

Exact HTTP(S) source/request URLs join bookmarks to exported source entries. Typed entry/insight/skill/session/session_turn nodes carry coverage, citations, caveats and provenance. Sessions are a third independently supplied corpus; part_of edges preserve recorded turn membership. Published entries carrying matching session_provenance turn revisions join to supplied turns with captured_from edges. Missing/changed pins produce no join; URL mentions in session prose never create bookmark links. Supplied paths and handoff argument arrays remain inert display metadata. Typed IDs require supplied records and never trigger implicit companion access.

`knowledge-links.json` is authored state in the CLI home. Reviewed references pin supplied revisions with reasons and timestamps. SQLite serializes writers; the sidecar must match the loaded snapshot before atomic replacement. Changed supplied pins are reported and excluded. A supplied snapshot cannot verify later edits to foreign libraries. Neither relationships nor hashes grant authority.

Combined search preserves producer ranks only for the exact exported query. Other interactive queries use explicit snapshot lexical ranking over supplied metadata. Corpora retain separate ranks; one bounded context layer follows direct hits and reports omissions. Immediate details avoid bookmark vectors; full graph navigation retains all supplied relationships. CLI, terminal and browser graph paths share these primitives. No external process, Neon migration, public projection, active-skill change, new database or resident model belongs to this boundary.

## Reviewed public publication

`importer.rs` exposes a destination-bound review plan with every structurally eligible unique URL, all origins, evidence and duplicate/pruned status. Semantic ranking helps review; it cannot authorize selection. Human review starts with nothing selected and requires per-URL choices plus PUBLISH N. Agent apply requires the checksum of the selected plan. URL/title changes invalidate approval. Complete selected inputs validate before any write.

`database/bookmarkdrop.sql` is an administrator-reviewed PostgreSQL 16+ migration, activated on rsnair.tech production on 2026-10-11 after isolated Neon branch verification. Activation preserved all 3,336 existing public bookmark rows. The additional blog payload whitelist was separately approved and activated on 2026-10-11 by the coordinated connector chat after isolated branch and rollback/reapply checks. `database/blog-kind-upgrade.sql` and `blog-kind-rollback.sql` guard the exact function fingerprint; isolated branch checks do not establish a full restricted-role regression pass. It creates a nonlogin function owner, a restricted publisher login, origins, receipts and authored relationships. The publisher receives function execution, no direct source-table writes or owner membership. Fixed-search-path SECURITY DEFINER functions publish only source bookmarkdrop, preserve existing public titles, and retain annotations outside the public feed. URL dedup and all-source tombstone checks use the existing rsrch-ingest/pruning transaction lock 20771123. Archived origins are excluded from Neon reads unless the URL remains publicly active. Site read-only APIs and their projection remain unchanged.

Runtime injection uses the explicit BKD_* environment contract. The Neon URL must name a restricted publisher configured by the database administrator. Provider secrets remain outside cache exports and review plans; no CLI-specific secret manager abstraction is required.

Receipts bind deterministic batches to host/port/database/user. Pending journals precede remote writes and disappear only after confirmed receipts. Retry validates every journal/checksum/destination before writing. Batches are atomic; an entire multi-batch import is not. Partial failures expose confirmed batches and the uncertain operation. Reapplying the same reviewed plan uses receipts for already-completed batches. Migration rollback disables/revokes publisher access; it does not delete metadata or public rows.

## Surfaces and trust boundaries

The terminal graph uses full-screen, terminal-sized paging, label search, pan/zoom, list/details overlays and keyboard exit with terminal restoration. Layout proximity has no semantic meaning.

Bare `bkd` opens a quiet Ratatui capture canvas without querying the library or starting a model. The explicit `tui` subcommand is removed. `capture.rs` composes terminal search, bookmark filters, inert styled Markdown previews, graph navigation, editable single-link capture, and destination-bound per-URL import review. `bkd --plan FILE` resets selections before human review of an agent-generated plan. Bracketed paste opens a draft, never publication; ordinary HTTP key input also enters capture. Graph paste hands the URL back to the capture screen. Confirmation requires an exact PUBLISH count, is cleared by selection/edit changes, and cannot be pasted. The existing importer owns all writes and receipts. A confirmed write is distinct from a subsequent failed Neon cache refresh; new vectors remain an explicit offline sync. Terminal restoration covers normal exit, cancellation and errors. Network operations retain existing database timeouts. The HTML viewer is retained alongside the TUI by user request. Safari-to-WezTerm drops deliver no input: installed WezTerm 20240203 macOS native handling accepts file paths rather than Safari URL payloads; copy/paste works. Computer Use refused terminal access.

`bkd ui` is a Finder-style viewer with source sidebar, name-sorted 100-row library pages, relevance-ordered local search, link drag/paste capture, and Space/double-click Quick Look. Drops require one validated URL; safe plain text preserves exact spelling only when its parsed URL equals the URI-list URL, avoiding browser-added root slashes without trusting conflicting payloads. Cached metadata and notes come from the existing cache and retrieval primitives. The viewer does not fetch pages during listing or search. Capture edits clear publication confirmation; only the existing authenticated save endpoint and importer publish URL/title pairs. Saved notes/citations and graph navigation remain available. `DESIGN.md` maps the visual conventions and files.

The browser binds only loopback, embeds local assets, consumes a single-use launch token, and requires an HttpOnly SameSite session cookie. Host, Origin, method, content type and body size are checked. Public saves require an explicit checkbox and confirmed receipts. Cached Markdown disables raw HTML, images and embedded links. Quick Look explicitly loads the validated HTTP(S) bookmark in an iframe with an empty sandbox and no referrer; scripts/forms/top navigation are disabled. Remote site embedding restrictions remain authoritative. CSP permits HTTP(S) frames while scripts/styles/connections remain local; no CDN or inline scripts. This local UI is not a remotely hosted service.

`reader.rs` handles the explicit authenticated same-origin POST `/api/reader`. It validates each HTTP(S) URL and redirect, rejects custom ports and private/reserved addresses (including mixed DNS answers), pins checked addresses, disables proxies and sends no browser cookies or auth. At most five redirects and 2 MiB UTF-8 HTML are accepted, with a 20-second HTTP budget; OS DNS lookup follows its own resolver timeout. The foreground server is sequential, so a fetch may temporarily block other requests. The browser parses fetched HTML only in inert template contents, selects article/main text heuristically, and inserts newly created text nodes only. Images, scripts, frames, forms and navigation never enter the reader. Reader output is temporary and bounded to 200,000 characters; no indexing, canonical-source mutation or implicit publication occurs. It does not support JS-only, authenticated or PDF content, and may omit peripheral article content.

## Extension points and invariants

A connector reuses the bounded transport, Record validation, complete-snapshot publisher and shared ranking. Add its normalized reader, provider/auth/CLI registry choices and contract tests together. No connector-specific ranking or publication policy is allowed. Winnow may be added as an explicitly enabled local decision helper later; it is not a runtime dependency.

- Partial scans and stale concurrent refreshes cannot erase the previous complete snapshot or newer authored edits.
- Exact URL copies produce one ranked bookmark; all origins remain exportable.
- Source filters cannot consult excluded annotations or vectors.
- Model output never grants publication authority.
- Public publication cannot restore tombstoned URLs or overwrite another source's title.
- Save success derives from confirmed receipts, including pruning races.
- Website readers cannot access annotation functions.
- No credential reaches logs, browser assets or review plans.

Update this document with cache/storage recipes, provider contracts, taxonomy, runtime entrypoints or trust-boundary changes. Verification evidence and remaining gaps are in docs/verification.md.

## Workflow records
Explicit skills knowledge-snapshot/v2 packets may contain workflow nodes with
workflow: scoped IDs and hash-bound revisions. Search/graph use supplied records.
Existing v1 packets remain readable saved data. No runner, companion process,
skill body or private index is read or invoked by bkd.

## Portable distribution
The source bootstrap sets BKD_HOME to its own empty state. It does not configure
connectors or perform public writes. Persistent keychain auth is macOS-only; other
platforms require explicit BKD_* credential injection and fail before keyring use.
