# distiller Architecture

## Purpose

`distiller` turns URLs, local HTML files or stdin snapshots into clean article
content, with Markdown, JSON, EPUB3 and optional Kindle KFX outputs.
Born-digital local PDFs have a separate Rust/PDFium reflow path to EPUB.

Primary contract:

```bash
distiller <url> -o webpage.md
```

## Design Principles

- Keep the default path deterministic and fast.
- Represent HTML as a DOM for structural cleanup; avoid nested regex over tags.
- One markdown converter (`markdown_ast`) plus markdown post-processing helpers.
- Isolate site-specific behavior in extractors.
- Keep acquisition concerns separate from extraction concerns.
- Prefer simple module seams over heavy abstractions.

## High-Level Flow

```text
URL
  -> fetch (HTTP, size-capped stream decode, optional Medium RSS / browser fallback)
  -> Html::parse_document once
  -> site extractor OR readability/content find
  -> DOM cleanup (selectors, hidden, images, scoring, chrome patterns)
  -> metadata extraction
  -> markdown_ast conversion + chrome postprocess
  -> optional LLM override (--llm), gated against heuristic markdown
  -> output file (markdown/json) OR sandboxed Pandoc EPUB3 packaging
```

## Module Layout

```text
src/
├── main.rs                 CLI
├── kfx.rs                  CLI-only adapter to independent local EPUB-to-KFX encoder
├── lib.rs                  Pipeline orchestration
├── types.rs                Options/response types
├── epub.rs                 Bounded image embedding and atomic Pandoc EPUB3 export
├── cover.rs                Mandatory Muse artwork, local lettering and verified cover cache
├── pdf.rs                  Isolated native PDF worker, page reflow and figure extraction
├── pdf_reconstruct.rs      Source-linked OpenRouter reconstruction, validation and rendering
├── fetch.rs                URL acquisition and fallbacks
├── dom_ops.rs              Fragment parse/serialize + node detach helpers
├── extractors/             Site-specific extractors + registry
├── find_content.rs         Main content candidate discovery
├── removal/                DOM-based cleanup passes
├── standardize/            Footnotes/callouts
├── metadata.rs             Title/author/date/site/meta extraction
├── markdown_ast.rs         DOM-walking markdown conversion
├── markdown.rs             Markdown post-processing helpers only
├── extraction/
│   ├── llm.rs              --llm provider orchestration
│   └── checks.rs           LLM safety/quality gates
└── observability.rs        Structured debug logging
```

## Pipeline Contracts

### Acquisition Contract

- `fetch::fetch_page(...) -> Result<String>`
- Returns decoded HTML only.
- Bodies are streamed with a hard byte cap (`MAX_SIZE`).
- Medium `Referer` is applied only for Medium hosts.
- LLM provider calls are not part of fetch.
- Browser fallback exists only when built with `--features browser`.

### Extractor Contract

- `fn extract(&Html, &str) -> Option<ExtractorResult>`
- Returns `content_html` plus optional metadata overrides.
- Registry owns URL-pattern dispatch.

### Cleanup Contract

- Removal stages operate on `scraper` DOM fragments via `dom_ops`.
- Serialize once per stage (or after detach).
- Nested HTML-eating regex is intentionally avoided for structural pruning.
- Heuristic pruning protects code, math, tables, superscripts and subscripts.
  Exact chrome/security removal still runs.
- Sanitization and URL resolution edit DOM attributes, never literal code text.
  This is extraction hygiene, not a complete HTML rendering security boundary.

### Output Contract

- Extraction and conversion produce standalone files for downstream tools.
- CLI `--mode kfx` selects the existing EPUB extraction/cover path internally,
  then invokes the independent `epub-to-kfx` executable on a temporary EPUB.
  Library ParseMode and extraction semantics stay unchanged. The adapter checks
  encoder prerequisites and destination availability before extraction or cover
  spending. KFX export is file-only, supports HTML/stdin/PDF through their existing
  EPUB constraints, and has a 370-second conversion deadline. The independent
  encoder uses Amazon Previewer plus KFX Output, publishes with a no-clobber hard
  link, and owns its bounded process deadlines and cleanup. Amazon may resize and
  recompress images.
- `DistillerResponse` contains content, markdown, metadata, parse timings, and meta tags.
- `ParseMode` controls Markdown/JSON/EPUB output behavior. EPUB preserves the
  structured DOM rather than replacing it with a longer plain-text schema body;
  it retains footnote backrefs and defers URL resolution until images are embedded.
- Local files share the bounded strict UTF-8 input path with stdin. `--base-url`
  is optional for files and required for stdin; URL positional input rejects it.
- EPUB consumes cleaned HTML directly, includes trusted typography in page headers,
  and delegates EPUB3 packaging, metadata, heading navigation and chapter splitting
  to Pandoc on PATH (tested 3.12.1). Pandoc runs with `--sandbox`, warning failures
  and uses explicit extracted title metadata before a first-heading fallback.
  It has a 30-second timeout. Missing Pandoc fails without publishing output.
  Every EPUB requires a cover. `--cover` overrides generation with a decoded PNG/JPEG (4 MiB maximum,
  included in the 64 MiB total) and works through the same packager for PDFs.
  Pandoc 3.12.1 needs the owned cover copy supplied as both cover-image and
  reference-doc to preload that file in its sandbox; no directory access is granted.
  The EPUB writer ignores reference-doc otherwise. Distiller owns this workaround;
  remove it when Pandoc's cover option itself preloads correctly.
  Wrappers containing headings are flattened while retaining their IDs as inline
  anchors, because Pandoc excludes headings nested in Div blocks from its TOC.
  Heading wrappers with language/direction attributes fail explicitly until
  flattening can preserve their inherited semantics.
- EPUB embeds decoded PNG/JPEG/GIF bytes as data URLs (4 MiB each, 64 MiB total);
  local regular files must canonicalize beneath the input HTML's parent directory.
  HTTP(S) assets are streamed with a 10-second request timeout, five redirects and
  the same byte caps in URL/file modes. Stdin permits only inline data images.
  Decoding caps dimensions at 12000 per axis and allocations at 128 MiB; WebP
  becomes lossless PNG. Unsupported media fail explicitly. Dates are normalized
  to ISO dates; unparseable dates are omitted. Paragraph/list-item IDs become inline anchors because Pandoc drops
  those container IDs. Atomic no-clobber publication protects existing books.
- HTML EPUB extraction/packaging is deterministic and file-only; PDF reconstruction and cover artwork use models.
  Muse (`muse-image-1.0`, fixed https://api.meta.ai/v1/responses) generates one
  text-free illustration on a cache miss, with a 90-second deadline, no redirects,
  an 8 MiB response cap and 4 MiB PNG cap. Only title, author and six bounded
  section labels are sent. A bundled SIL OFL Noto Sans Bold font typesets exact
  title/author on opaque panels in a 1024×1536 grayscale cover. Unsupported
  glyphs/shaping and unreadable overflow fail before dispatch; precomposed Latin,
  Greek and Cyrillic are supported, combining marks and complex scripts are not.
  The source content fingerprint includes the PDF's existing source SHA-256 ledger.
  Cache identity binds source, metadata, font, prompt/profile and Muse settings.
  PNG iTXt provenance travels inside the EPUB; a receipt hashes the final image.
  Cache image/receipt files and directory publication are synchronized before
  deleting the exclusive reservation; this requires filesystem directory-sync support.
  Completed cache survives packaging failure; no expiry or background eviction.
  Pending requests wait at most five seconds, then fail without retry. Recovery
  requires checking provider history before explicitly removing the named `.pending`
  file. Cache corruption is an error, never a hidden paid regeneration.
  `DISTILLER_COVER_CACHE` defaults to `~/.cache/distiller/covers`; runtime
  `DISTILLER_MUSE_API_KEY` is needed only for a cache miss (`MODEL_API_KEY` is ignored with a hint). No generation enable/disable flag.
  EPUB rejects extraction LLM/stdout modes. Multi-article
  books remain unsupported; EPUBCheck verifies packaging, not
  source fidelity or reading-system display.
- PDF uses PDFium 7881 from ~/.local/share/distiller/lib or the system library
  path, in a child Rust process with a 180-second extraction timeout. Input limits:
  200 MiB, 400 pages, 100000 characters/objects per page, Form depth 16 and
  32 million pixels per image. No Python production runtime or OCR is used.
  The worker retains all non-whitespace glyphs in stable text spans, including
  PDFium's line-end hyphen flag, font size, x/y geometry and source-page identity.
  It emits a JSON layout rather than guessing body/note regions or flattening
  columns. `pdf_reconstruct.rs` submits owned page pairs plus adjacent-page
  context and 1200×1800-bounded grayscale page previews (1 MiB JPEG each) to
  OpenRouter `deepseek/deepseek-v4.1-flash`, requesting strict JSON
  Schema and endpoints requiring parameter support. PDF text and page previews are sent to
  this model; covers still receive only bounded metadata. No local model download.
  Output assigns span IDs and bounded join operations to paragraphs, headings,
  quotations, list items, notes, tables and figures; it cannot replace prose.
  Every owned span/image must occur exactly once. Arbitrary fields, unknown IDs,
  invalid hyphen removals, broken note targets, and unsupported furniture
  classifications fail validation. Digit-bearing terms cannot request
  dehyphenation; ambiguous source hyphens remain. Furniture eligibility uses
  page-edge and repeated-position/page-number evidence; semantic classification remains heuristic.
  Source SHA-256 remains in a nonvisible HTML comment for cover identity.
  Notes move to an end section, with backlinks when a matching numeric callout
  is explicitly associated. Page anchors are invisible; no generated page labels,
  raster captions, blank-page prose or conversion warnings enter the reading flow.
  Source bookmarks guide actual heading placement; unmatched bookmarks remain
  in the evidence layout and are not fabricated as body headings.
  Requests use low reasoning with a 32768-token output budget, a 300-second
  deadline and 2 MiB response cap, with at most three
  validation attempts per page pair and no model fallback. OpenRouter selects
  the serving endpoint; the provider is recorded with usage. Truncated
  responses fail. Validated pairs are atomically cached under `DISTILLER_PDF_CACHE`
  (default `~/.cache/distiller/pdf`) with source/model/prompt/endpoint identity;
  cache hits are revalidated. Raw responses, usage and an HTML/hash receipt support
  inspection and resume. Corrupt cache fails explicitly. `OPENROUTER_API_KEY` is
  injected only at runtime; test endpoints permit HTTP only on loopback.
  Nested Forms are traversed; rotated/skewed/stretched Forms, rotated/mirrored/skewed
  images, scans and graphic-only
  pages fail. JPEG bytes survive only if PDFium raw/processed pixels match;
  other rasters use lossless PNG with adaptive compression and EPUB byte caps.
  Images render at integer source-pixel scale, with the original matrix restored.
  Model-selected ordering, table cells, joins and note associations still require
  source comparison; ID coverage does not prove semantic fidelity. Equations,
  vector graphics, clipping, original link annotations and emphasis are not
  reconstructed by this slice. Unsupported graphics warnings are retained in
  the reconstruction receipt and counted on stderr, outside the book body.
- `--stdin --base-url URL` reads bounded (5 MiB), strict UTF-8 HTML and calls
  `parse_html` without source fetching or extraction LLM use. EPUB's mandatory
  cover can make a separate outbound Muse request. Conflicting acquisition/LLM flags fail
  before input is consumed. Stdin defaults to stdout; explicit output paths remain.
- Stdin JSON is `article-extraction/v1`: exact caller-supplied source URL, SHA256
  of input bytes, HTML/UTF-8 media identity, extractor version/method/options,
  and title/Markdown. URL JSON retains its existing `DistillerResponse` shape.
  This is a data contract, not a downstream tool dependency or review receipt.
- Fenced code keeps source text, indentation and blank lines; a terminal newline
  is added only when required to close a fence. Delimiters exceed source backticks.
- Inline text follows DOM boundaries; numeric content and inline code spaces survive.
- Math uses single-line TeX annotations when available; multiline annotations remain MathML, otherwise sanitized MathML.
  Superscripts/subscripts retain semantic HTML.
- Rectangular tables with a header row use GFM with empty cells intact. Spanning,
  mixed-header or nested/block tables retain sanitized HTML instead.
- Prose cleanup skips code and semantic HTML/TeX. Whole-HTML whitespace and entity
  rewriting is absent. HTML/math display depends on the consumer's renderer.

## Runtime Modes

### Default Mode

- Heuristic extraction pipeline only.
- Fast and deterministic.

### `--llm` Mode

- Runs after the heuristic pass.
- Safety checks compare candidates to heuristic markdown (not raw page markdown).
- Falls back to heuristic output automatically.

## Recovery

- At most one relaxed retry when word count is below threshold.
- Retry disables partial selectors, content-pattern pruning, and low-score pruning together.

## Observability

With `--debug`, JSON logs are emitted to stderr.

Current tracked events include:
- pipeline start/done
- fetch attempts and outcomes
- per-removal step deltas (word/char counts)
- LLM pipeline outcome
