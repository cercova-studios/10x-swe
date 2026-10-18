# distiller

`distiller` extracts readable article content from URLs or UTF-8 HTML files and writes Markdown, JSON, EPUB3 or Kindle KFX.

Core CLI contract:

```bash
distiller <url> -o webpage.md
```

## Quickstart

The shared package excludes Kindle delivery and device configuration. The generic
optional KFX adapter requires an independently supplied `epub-to-kfx` converter;
EPUB, Markdown and JSON remain independent of it.

### Make a readable EPUB

```sh
distiller article.html --mode epub -o article.epub
distiller article.html --base-url 'https://example.org/article' --mode epub -o article.epub
distiller 'https://example.org/article' --mode epub -o article.epub
distiller article.html --mode epub --cover cover.png -o article.epub
```

EPUB export requires Pandoc on `PATH` (tested with 3.12.1). It uses cleaned HTML
directly, retains structured DOM instead of plain-text schema replacements, and
adds a title page, heading navigation, chapter breaks, metadata and reader-friendly
typography. It preserves code tabs, MathML, spanning tables and footnote links.
Pandoc can normalize terminal code newlines; equation display depends on the reader.

Every successful EPUB has a cover. On a cache miss, Muse generates text-free
artwork and Rust composes exact title/author text using a bundled licensed font.
Explicitly configure MODEL_API_KEY only when authorizing cloud cover generation:

```sh
distiller article.html --mode epub -o article.epub
```

`--cover PATH` overrides generation with a supplied PNG/JPEG for reader libraries,
including Books. The regular file must decode within the image limits and be at
most 4 MiB; its bytes count toward the 64 MiB total. It works with HTML, stdin
and PDF EPUBs/KFX files and is rejected for Markdown/JSON. Supplied and verified cached
covers need no credential or image request. No generation toggle is required.
Missing credentials, invalid responses, timeouts and unsupported typography fail
without publishing an EPUB. Markdown/JSON never generate covers.

Generated covers are 1024×1536 grayscale PNGs with large local title/author text,
opaque panels and a geometric illustration. Precomposed Latin, Greek and Cyrillic
are supported; complex scripts/combining marks require a supplied cover. Muse is
asked for artwork without text, but unintended model-drawn symbols in the artwork
are not detected. Physical e-ink display quality remains a reader acceptance check.

The cache defaults to `~/.cache/distiller/covers`; `DISTILLER_COVER_CACHE` overrides
the directory. Entries contain `cover.png` and a hash-checked `receipt.json`;
PNG provenance also travels inside the EPUB. There is no automatic eviction.
One request is attempted per miss, with a 90-second deadline and no redirects.
Meta's published rate is $0.01 per returned image; actual billing is not reported
by distiller. Failed/interrupted requests retain a `.pending` reservation because
billing may be uncertain. Check provider history before explicitly removing that
named reservation. Corrupt entries require explicit restoration/removal, not a
silent paid retry. Atomic cache publication requires directory synchronization.

The first version creates one article per book. It embeds local, base64 or HTTP(S)
PNG, JPEG and GIF images, with 4 MiB per image and 64 MiB total. Images must decode
within dimension/allocation caps; WebP is converted losslessly to PNG. Local images must stay
beneath the HTML file's directory, including symlinks, and must be regular files.
Remote requests have a 10-second timeout and five-redirect limit. Unsupported
media, SVG and MathML image glyphs cause an error. Pandoc runs in its sandbox
with a 30-second timeout. Existing EPUBs
are never overwritten; failures leave no partial destination.

EPUB accepts stdin with `--stdin --base-url URL --mode epub -o article.epub`.
It rejects `--llm`, `--stdout` and `-o -`. Local HTML files accept at most 5 MiB
of strict UTF-8 and reject `--llm` and `--proxy`.

Run the public CLI journey after building:

```sh
python3 tests/epub_journey.py --binary target/debug/distiller
# Optional independent conformance check:
python3 tests/epub_journey.py --binary target/debug/distiller --epubcheck /path/to/epubcheck.jar
```

### Reflow a born-digital PDF

```sh
distiller ~/books/situationalawareness.pdf --mode epub -o situationalawareness.epub
python3 tests/pdf_journey.py --binary target/debug/distiller --epubcheck /path/to/epubcheck.jar
```

The converter is Rust, using `pdfium-render` and PDFium 7881. Install the matching
platform library from [PDFium's binary release](https://github.com/bblanchon/pdfium-binaries/releases/tag/chromium%2F7881)
in `~/.local/share/distiller/lib` (or the system library path), preserving its license.
Pandoc packages the final EPUB. Python and ReportLab/Pillow are test dependencies only.

The worker accepts up to 200 MiB and 400 pages and stops after 180 seconds. It
extracts text spans with stable IDs, font/position evidence, bookmarks and raster
figures. Original JPEG bytes are
kept when their decoded pixels match PDFium's processed output; other figures use
lossless PNG. Image and page-object limits fail explicitly instead of dropping data.
Scans, graphic-only pages, rotated/skewed/stretched Forms and rotated/mirrored/skewed
images are rejected. Figures render at integer source-pixel scale to avoid resampling.

PDFs then use `deepseek/deepseek-v4.1-flash` through OpenRouter with strict JSON
Schema. The model sees source text
and geometry plus bounded grayscale page images and returns source-linked blocks,
tables, note associations and joins;
it cannot rewrite the prose. This sends the PDF text to a cloud provider, without
downloading a local model. Supply `OPENROUTER_API_KEY` explicitly at runtime.
The ordinary HTML extraction path remains deterministic.

Rust requires every source span/image exactly once and rejects invalid references,
joins and furniture removal. Explicit hyphen repairs cannot remove ordinary literal
hyphens. Digit-bearing terms retain ambiguous trailing hyphens rather than risk
deleting a compound separator; rare wrapped alphanumeric words may retain a line hyphen.
The model selects printed heading positions; notes move to a separate
end section with links when associated. Generated `Source page` labels, generic
raster captions and blank-page notices are gone. A source-page anchor stays invisible.

Each page-pair request uses low reasoning and a 32768-token output budget,
a 300-second deadline, a 2 MiB response cap and at most
three validation attempts. Incomplete responses fail without publishing output.
Accepted page pairs are cached and revalidated on resume under `~/.cache/distiller/pdf`
(`DISTILLER_PDF_CACHE` overrides it). Source layout, model responses, provider usage,
reconstructed HTML, source hashes and warnings remain there for inspection. Cache
corruption is an error. Conversion and downstream delivery remain separate outcomes.

Model-selected reading order and semantic associations still need source inspection.
Equations, vector graphics, clipping, original link annotations and emphasis are
not reconstructed. Graphics warnings are retained in the receipt and counted on
stderr, rather than inserted into the book. Language defaults to English.
Packaging validity and source-ID coverage do not establish semantic fidelity or
correct display on every reading device.

### Pipe a retained HTML snapshot

```sh
distiller --stdin --base-url 'https://example.org/article' --mode json < source.html
```

`--stdin` accepts at most 5 MiB of UTF-8 HTML and writes stdout by default.
Extraction performs no source fetching or LLM calls; EPUB cover generation can
separately call Muse. Stdin conflicts with the URL argument,
`--llm`, `--proxy`, and `--lang`. `--base-url` preserves the exact original URL
and resolves relative links. Markdown remains the default output mode.

JSON stdin output uses this producer-neutral record contract:

```json
{
  "schema": "article-extraction/v1",
  "source": {"url": "https://example.org/article", "sha256": "<64 hex digits>", "media_type": "text/html", "encoding": "utf-8"},
  "extractor": {"name": "distiller", "version": "0.1.0", "method": "deterministic-html", "options": {}},
  "document": {"title": "Article title", "markdown": "Extracted Markdown"}
}
```

The input hash covers exact stdin bytes, not normalized HTML. Empty options mean
the version's deterministic parser defaults. Source URL labels are supplied by
the caller; a hash does not authenticate authorship or establish source fidelity.
URL-mode JSON keeps its existing response format. Neither mode invokes a consumer,
stores knowledge, or reviews claims. Use shell `pipefail` when composing producers.

### Install the CLI

From the repository root:

```bash
cargo install --path plugins/knowledge/tools/distiller --locked
distiller "https://example.com/article" --stdout
```

Cargo installs `distiller` in `~/.cargo/bin` by default. Ensure that directory is on `PATH`.
To include optional browser fallback, add `--features browser` to the install command.

### 1. Build

```bash
cargo build
```

### 2. Run (default markdown output)

```bash
cargo run -- "https://example.com/article" -o webpage.md
```

### 3. Choose output mode

```bash
# JSON
cargo run -- "https://example.com/article" --mode json -o webpage.json
```

### 4. Enable LLM extraction pipeline

```bash
cargo run -- "https://example.com/article" --llm -o webpage.md
```

The default LLM provider is Ollama's [`gemma4:31b-cloud`](https://ollama.com/library/gemma4:31b-cloud), with no secondary
provider fallback. If it fails or its output fails the quality checks, extraction
keeps the heuristic output. `DISTILLER_LLM_PROVIDERS` overrides this default.

Optional environment variables:

```bash
export DISTILLER_LLM_PROVIDERS="gemma4:31b-cloud"
export DISTILLER_LLM_TIMEOUT_MS=12000
export DISTILLER_LLM_MAX_INPUT_CHARS=60000
export OLLAMA_BASE_URL="http://127.0.0.1:11434"
export JINA_API_KEY="..."
```

### 5. Enable browser fallback support

Browser fallback is behind a feature flag:

```bash
cargo run --features browser -- "https://example.com/article" -o webpage.md
```

### 6. Run tests

The cover regression journey requires Pandoc and Python 3 on `PATH`; it uses a
local mock Muse server and makes no paid requests. PDF journeys additionally
need PDFium and the test-only ReportLab/Pillow dependencies.

```bash
cargo test
```

## Attribution

This project is inspired by the extraction approach and architecture patterns from [`defuddle`](https://github.com/nicholasgasior/defuddle).
`distiller` is an independent Rust implementation with its own pipeline, CLI, and module layout.

## Deterministic fidelity

The default path preserves highlighted code values, indentation and blank lines.
Inline code spaces and numeric paragraphs survive cleanup. MathML and sup/sub
retain semantic HTML; single-line TeX annotations become math delimiters; multiline annotations remain MathML. Simple
tables retain empty cells and links; complex tables remain HTML. A compatible
renderer is required for math and raw HTML. Sanitization edits real DOM attributes
and does not rewrite attribute-like strings inside code.
