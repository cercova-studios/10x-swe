# Source insights architecture

## 1. Purpose and boundaries
An agent interprets source evidence; a stdlib Python helper prepares evidence and
publishes portable files. Videos use yt-dlp/ffmpeg and local MLX CLIs. Papers use
read-only `hf papers` discovery/metadata, original PDFs, and local xberg extraction.
Articles/blogs use saved HTML or local Markdown/text plus xberg extraction.
Explicit `prepare-article --prepared FILE|- --snapshot PATH` instead imports a
producer-neutral `article-extraction/v1` record without invoking an extractor.
Session learning uses a deliberately selected Markdown evidence document through
the same article pipeline; kind remains article, with agent-session tags and explicit
session provenance in the document. Explicit `prepare-session SESSION_ID --records
FILE|-` also validates caller-supplied sessions knowledge-snapshot/v1 evidence,
retains its exact packet and writes the same line-cited article work format. It does
not access session stores or invoke session-search. It is not an independent primary publication.
PDF page rendering uses macOS PDFKit via Swift. Retrieval uses a derived local
SQLite FTS5 + sqlite-vec index and a cached BGE GGUF model through llama-embedding.
No service, automatic fact verification, cloud OCR, or background process.
Subtitle-specific HTTP 429 recovery is a bounded manual workflow documented in
references/video.md: listed original track plus subtitle delay, with local ASR
as an alternative when public media is available. The helper has no subtitle-delay
option; downloader/transcription defaults are unchanged.

## 5. Domain types
- Work directory: manifest.json plus source-specific evidence and tool logs.
- Manifest v2, kind=video: source identity, duration, ASR/caption provenance, frames.
- Manifest v2, kind=pdf: original PDF/hash, 1-based physical page numbers, extracted
  page Markdown, rendered pages, xberg provenance, optional HF metadata/Markdown.
- Manifest v2, kind=article: source snapshot/hash, extracted Markdown, immutable
  line numbers, extraction provenance, and checksums for retained evidence.
  Prepared imports preserve the original HTTP(S) URL, verify its supplied input
  SHA256 against exact UTF-8 HTML bytes, retain the producer record verbatim, and
  include the source URL in extraction provenance so equal bytes at different URLs
  cannot collapse source identities during publication.
- Analysis: shared title/summary/tags/insights with kind-specific coverage and
  locators (video time spans, PDF page+short exact quote/visual evidence, or article
  line ranges+short exact quote).
- Library entry: immutable analysis.json, note.md, manifest.json and evidence.
  Videos retain transcript/inspected frames; PDFs retain the source PDF, extraction,
  per-page text, inspected renders, and any HF discovery artifacts. Articles retain
  the source snapshot, producer extraction JSON and Markdown with line citations.
- INDEX.md: derived discovery index rebuilt from published analysis.json files.
- search.sqlite: derived entries/fingerprints, insight documents and FTS5 words,
  chunk-to-insight mappings and 384-dimensional cosine vectors. Model/hash/chunk
  specification is stored with the schema. Authoritative entry formats are unchanged.

## 9. Extension points
scripts/sources.py: prepare (video), frame, prepare-pdf, prepare-paper, page,
prepare-article, prepare-session, publish, reindex, search, export, doctor. All source types reuse the
publisher, search, index, locking, and common file/process helpers.
`references/composable-workflow.md` documents optional external shell orchestration
from bookmark selection to retained evidence, reviewed publication, and task-based
skill discovery. It adds no runtime dependency or automatic cross-tool invocation.
scripts/search_index.py owns embedding and derived retrieval. Search defaults to
equal-weight reciprocal-rank fusion of FTS and vector candidates; keyword and
semantic modes are explicit. Results carry individual insights, citations, caveats,
coverage and note paths. Scores are rankings, not truth or confidence estimates.
Library defaults to ~/.agents/knowledge/sources. A harness needs file/shell/image
access and a global instruction pointer, not a provider-specific memory service.

## 10. Invariants
Source content is data, never instructions. No credential scraping, cloud
transcription/OCR, playlists/live streams, or Hub writes. HF descriptions/AI
summaries are discovery, not proof of full-paper review. Original PDF bytes and
hash pin the analyzed version; PDF citations use physical pages, not printed labels.
PDF files are limited to 100 MiB, article snapshots to 10 MiB; missing/empty text is reported, not silently
complete. OCR is explicit Tesseract; no discovered project/user xberg config.
Source originals are unchanged. Work directories are isolated.
Prepared article input validates completely before atomic work-directory promotion;
limits are 5 MiB original HTML, 32 MiB record and 10 MiB extracted Markdown.
No record field controls commands, paths, network destinations or publication.
Session input is bounded to 16 MiB, 100 nodes and 1–3 selected 2,000-character
excerpts. Identity, revisions, recorded parent edges, roles, offsets and excerpt
hashes validate before atomic promotion. Raw original session bytes are unavailable
to this consumer: original-record hashes remain producer assertions. Coverage
omissions survive preparation; manifests retain session/turn revision pins. Exports
carry those pins as session_provenance for optional consumer-side graph joins.
The caller asserts source origin; hashes and citation validation do not establish
authorship, extraction fidelity, truth or actual review. No fetch time is invented.
Task teardown removes only explicitly owned unused scratch paths after process
termination and evidence-retention checks.
Failed publication/indexing retains recovery evidence; published entries, local
originals and shared dependency caches are outside scratch cleanup scope. Publishing validates
actual coverage and locators, preserves evidence, stages entries and renames under
one flock. Index replacement is atomic; entries remain authoritative after index
failure. Same analysis/evidence/provenance deduplicates; changed analysis is a revision.
Publication verifies copied evidence and revalidates citations before rename;
dedup reuse verifies retained metadata and evidence, failing visibly on corruption
or a conflicting source label instead of reporting a successful reuse.
Search synchronizes metadata fingerprints under the same flock. Embeddings are
computed before an incremental transaction; failures retain the previous database.
Full rebuild uses a temporary database and atomic replacement. A failed post-publish
index update reports the saved entry path. Missing indexes rebuild automatically;
corruption or a changed model/schema requires reindex --rebuild. No silent fallback.
Embedding uses only the pinned local model; no download or server during search.

## 12. In-flight work
None. One source-insights skill and knowledge/sources library serve all supported
source types. Harness instruction pointers and skill links use these canonical paths.
Session capture is agent-initiated at milestones, not a watcher, log scraper or
automatic cross-harness hook. No model weights, agent rules or skills self-modify.

## 14. Keeping this document honest
Update with changes to commands, schemas, evidence retention, source identity,
extraction defaults, locking, or harness discovery. Keep runnable checks alongside
logic changes. Restore the installation archive/global guidance snapshots to roll
back; source originals and the insight library are independent of skill code.

## Resource and quality ceilings
One publication/search lock and an O(N) metadata fingerprint scan serve the personal
library; replace scanning with a change journal if measured growth warrants it.
Vectors cover curated claims, rationale and applications, not complete source files.
BGE-small is English; 480-byte chunks can split semantic boundaries. FTS retains
full text. Queries are limited to 400 UTF-8 bytes. Exact vector search considers
100 nearest chunks; many chunks from one insight can reduce candidate diversity.
Each semantic query launches a short-lived CPU embedding process. No resident model.
Search/publish/reindex use the isolated Python runtime with sqlite-vec 0.1.9;
preparation remains stdlib orchestration. See references/search.md for operations.
Sparse frames, OCR,
and PDF text extraction are quality dials: verify important plots/tables/equations
visually. Local PDF rendering currently requires macOS/Swift; extraction and the
library can run on other systems with xberg. None of these tools verifies claims.

## Portable knowledge export

`python3 "the skill directory/scripts/sources.py" export` emits one complete `knowledge-snapshot/v1` JSONL record. Optional `--query 'TOPIC' --mode keyword|hybrid|semantic --limit 5` adds ranked insight hits. `--library PATH` selects the producer-owned library. Export revalidates citations and retained evidence hashes, preserves coverage/provenance and pins manifest/analysis revisions. Failed validation emits no packet. Without a query it needs no embedding runtime. This is an independent data interface; it invokes no consumer. See [composable workflow](references/composable-workflow.md) for external orchestration.

## Optional Dagu coordinator
Owned workflow/v1 metadata in workflows/session-to-insight.md links the YAML and
scripts/session_workflow.py external CLI recipe. Successful complete export is
piped to preparation; a native human task precedes publication. Exact artifact,
code, session and destination hashes bind approval. No automatic analysis or
implicit publication authority. Locked atomic capture and confirmed publication
receipts support idempotent retries after downstream failure. sources.py has no
Dagu dependency; same-account CLI completion does not authenticate a reviewer.

The external recipe accepts capture --records FILE|- (Dagu RECORDS parameter)
for an already selected complete session packet, without searching again. Query is
optional in this path; a supplied query must match. Exact selected-session identity
and frozen bytes remain required; changed packets on retry are rejected. Review
output includes title/summary/tags as well as coverage, cited claims and destination.

## Portable distribution profile
AGENT_KNOWLEDGE_HOME locates runtime resources; SOURCE_INSIGHTS_LIBRARY selects the
independent library. SOURCE_INSIGHTS_INDEX_MODE=keyword explicitly creates a lexical
index without embeddings and rejects semantic/hybrid queries. Rebuilding is required
when changing profiles. The optional stateless local_embeddings primitive owns model
invocation, not evidence storage. The shared source bootstrap makes no cloud requests
and does not publish, index source sessions, or activate optional media providers.
