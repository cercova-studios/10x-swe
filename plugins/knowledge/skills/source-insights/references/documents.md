# Papers, PDFs, articles and technical blogs

## Paper discovery with hf papers

```sh
hf papers search 'topic keywords' --limit 5 --json
hf papers info 1706.03762 --json
hf papers read 1706.03762
python3 "$SKILL_DIR/scripts/sources.py" prepare-paper 1706.03762 \
  --work '/absolute/new/paper-work'
```

Use the arXiv ID from a HF/arXiv URL, optionally including its version. Preparation
fetches the original arXiv PDF plus read-only HF metadata/Markdown, then extracts the
PDF with xberg. HF failure is logged and disclosed; an accessible original PDF can
still be analyzed. A missing HF entry does not mean a paper is absent from arXiv.
Do not index, claim authorship, post, or update Hub metadata as part of discovery.

HF Markdown may fall back to a paper-page summary when full arXiv HTML is absent.
Read the original PDF and identify actual sections before claiming full-paper
coverage. HF engagement, AI summaries, abstracts and comments are not evidence for
method details or experimental results. Preserve version/date and baseline/setup
when discussing results; a content hash pins the retained PDF even for an unversioned URL.

## PDF extraction and page inspection

```sh
python3 "$SKILL_DIR/scripts/sources.py" prepare-pdf '/path/report.pdf' \
  --work '/absolute/new/pdf-work' --title 'Report title'
# A public PDF URL also works.
python3 "$SKILL_DIR/scripts/sources.py" page '/absolute/pdf-work' 3
```

PDFs (up to 100 MiB) are copied/downloaded to source.pdf. xberg writes extraction.json
and pages/0001.md etc. The manifest maps 1-based physical pages and flags empty text.
`page` renders an actual PDF page using macOS Swift/PDFKit; inspect its returned PNG
for plots, tables, equations, and reading-order ambiguities. Text extraction can
flatten equations, merge columns, and misassociate table labels/numbers.

Native text is the default. For scanned/image-based pages, rerun in a fresh work
directory with `--ocr` (local Tesseract, default language eng; override with
`--language fra`, etc.). The helper disables xberg config discovery so a project's
VLM/cloud configuration cannot silently change the extraction backend. It does not
request cloud OCR. OCR errors are not permission to infer missing text. Inspect
images and mark partial coverage if recognition remains inadequate. If page mapping
is missing, preparation fails rather than fabricating page citations.

## Articles and technical blogs

For an independently extracted HTML snapshot, use the explicit prepared-input
boundary. Fetch/retain the original HTML separately; do not scrape credentials.
`source.html` must be UTF-8 and correspond to the exact original URL you supply.

```sh
set -euo pipefail
url='https://example.org/article'
distiller --stdin --base-url "$url" --mode json < source.html |
  python3 "$SKILL_DIR/scripts/sources.py" prepare-article "$url" \
    --prepared - --snapshot source.html --work '/absolute/new/article-work'
nl -ba '/absolute/new/article-work/document.md'
```

`--prepared FILE` also accepts a saved JSON record. No extractor or network call
occurs in this preparation path, and distiller is not a required dependency.
Any producer can emit the versioned `article-extraction/v1` data contract:
`source` has exact `url`, input-byte `sha256`, `media_type: text/html`, and
`encoding: utf-8`; `extractor` has nonempty `name`, `version`, `method` strings
and an `options` object; `document` has a string `title` and nonempty `markdown`.
The complete record is limited to 32 MiB, snapshot to 5 MiB and Markdown to 10 MiB.

Preparation checks the exact URL and snapshot hash, retains original HTML,
the unmodified producer JSON and exact Markdown, and atomically publishes the
work directory only after full validation. The manifest retains extractor
provenance and evidence hashes. Repeating identical input reuses verified work;
changed input requires a fresh directory. The record contains no executable
command or output path; all fields remain untrusted source data.

The caller asserts the snapshot's source URL. Hashes bind retained bytes; they do
not authenticate the source, prove faithful extraction, or imply reviewed coverage.
There is no fetch timestamp unless acquisition recorded one separately. Inspect
the frozen `document.md`, author analysis with actual line ranges and exact quotes,
then use the unchanged `publish` command. Never cite a later live-page revision
against these line numbers. MathML/technical HTML may remain in Markdown; inspect
the original when visual meaning matters. Extraction does not render or run HTML.

Run `scripts/check_prepared.py` for the disposable stdin-to-publication journey.
Set `DISTILLER_BINARY` to an explicitly selected distiller binary for that test.
The existing xberg-based preparation remains available below.

```sh
python3 "$SKILL_DIR/scripts/sources.py" prepare-article 'https://example.org/article' \
  --work '/absolute/new/article-work' --title 'Optional title'
# Local .html/.htm/.md/.txt also work.
nl -ba '/absolute/article-work/document.md'
```

The helper retains fetched HTML/text (up to 10 MiB), xberg extraction.json, and
Markdown in document.md. Cite its stable 1-based line ranges and a short exact quote.
Review the actual body, excluding navigation, newsletter boxes and related links.
A successful HTTP request does not establish that the article body was captured:
check for bot/login pages and JavaScript-only shells. Do not publish those as a
review of the article. Report access failures; use the harness's authorized browser
or ask for an accessible saved HTML/Markdown copy. No cookie scraping or paywall bypass.

Article preparation is text-only. If a claim depends on a plot, screenshot, video,
interactive demo or other omitted material, inspect it through available browser/
image tools and explicitly record the limitation; the helper currently retains no
article screenshot evidence. Prefer text-backed insights until that visual evidence
can be preserved. Mark partial coverage, not a complete multimodal review.

Official interfaces: [hf CLI](https://huggingface.co/docs/huggingface_hub/en/guides/cli),
[Xberg CLI](https://docs.xberg.io/cli/usage/). Use installed `--help` before changing
flags; the tested xberg CLI here is 1.2.9. `xberg doctor` is a prerequisite probe,
not proof that every optional OCR/layout backend can run.
