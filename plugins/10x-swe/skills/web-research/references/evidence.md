# From web research to reviewed evidence

Use search results to select sources. Use inspected source passages to support
claims. Prepare the evidence behind the main answer, not merely a convenient page
that demonstrates the pipe. Each source gets its own snapshot, work directory and
analysis; keep the answer's cross-source synthesis separate.

## Select capabilities and preserve citations

For a bounded technical question, search and focused URL extraction are usually
enough. Exa's app connector does not expose Search `type` or Deep settings;
Parallel's app connector does not expose Search `mode` or all freshness controls.
Do not claim to have selected a mode that the tool schema cannot accept. A fetch
with live access allowed is not proof that the returned content was freshly crawled.

Save request arguments and the complete response before selecting excerpts.
Keep returned request IDs, dates, warnings and per-URL errors. When a connector
exposes only text and no provider request ID, record that absence; do not invent
an ID or describe the response as a full native API result.

- Link each material claim to the original supporting page and section. Prefer a
  versioned release, document version or immutable source revision when available.
  Check every material clause: evidence for a tuple limit does not also support a
  memory-limit claim. Add the missing passage or split/narrow the claim. Label
  proposed applications as inference when the source does not recommend them.
- Distinguish a provider's publication-date estimate, the source's own date/version,
  retrieval time and a source-code revision. Record missing values as unknown.
- Inspect the relevant passage, its conditions and nearby code. Excerpt results,
  character-limited content and responses containing ellipses establish partial
  coverage, even when the tool is called “fetch.” Fetch the missing context or
  narrow the claim. Provider summaries and confidence are not source quotations.
- If a later snapshot differs from the connector text, check the claim again.
  Never transfer connector line numbers or quote offsets to newly extracted text.
  If the source has changed, retain both versions and disclose the difference.

## Pipe an original HTML snapshot into preparation

Prerequisites: Python 3, curl and a `distiller` executable supporting
`--stdin --base-url URL --mode json`. Check `distiller --help` and the consumer's
`prepare-article --help` first. The commands below run from the marketplace root
with its `knowledge` plugin present. For a source-only distiller build, its
[README](../../../../knowledge/tools/distiller/README.md) gives the install path.
An activated knowledge installation also provides the `source-insights` command;
the Python entrypoint below supports preparation/validation without that setup.

Select a public HTML source that supports the answer; this URL is a runnable example.
Keep provider request/response artifacts alongside the returned task directory.
If task artifacts must stay in a designated workspace, first set `TMPDIR` to an
existing writable directory there. The recipe leaves the review packet in place.

```sh
set -euo pipefail
umask 077
repo="$PWD"
url='https://www.postgresql.org/docs/current/queries-limit.html'
work=$(mktemp -d "${TMPDIR:-/tmp}/research-review.XXXXXX")
curl --fail --silent --show-error --location --max-redirs 5 \
  --proto '=https' --proto-redir '=https' --max-time 60 --max-filesize 5242880 \
  --write-out '%{url_effective}\n' --output "$work/source.html.part" "$url" \
  > "$work/final-url.txt"
mv "$work/source.html.part" "$work/source.html"
date -u '+%Y-%m-%dT%H:%M:%SZ' > "$work/retrieved-at.txt"
distiller --stdin --base-url "$url" --mode json < "$work/source.html" |
  tee "$work/extraction.json" |
  python3 "$repo/plugins/knowledge/skills/source-insights/scripts/sources.py" \
    prepare-article "$url" --prepared - --snapshot "$work/source.html" \
    --work "$work/prepared"
nl -ba "$work/prepared/document.md"
printf 'Review directory: %s\n' "$work"
```

Use only actual UTF-8 HTML for this path. A connector's Markdown, an API JSON
response or a raw source-code file is not an original HTML snapshot. Do not wrap
those values in invented HTML and label it as the original page. For another
source format, use the consumer's appropriate documented route or retain a
partial research packet until an admissible snapshot is available.

`pipefail` makes a failed acquisition/producer/consumer visible. Do not continue
from a failed curl, empty response or unvalidated output. A network denial needs
the harness's authorized access path; it is not a reason to weaken the evidence
contract. The consumer checks the exact caller-supplied URL and input-byte hash;
it does not authenticate the source or prove that extraction preserved its meaning.
Retain `final-url.txt` and `retrieved-at.txt` with the acquisition artifacts; those
sidecars are not automatically included in the consumer's prepared manifest.

## Review the frozen text and stop before publication

Inspect `prepared/document.md` against the original source. Identify missing
sections, diagrams, code or navigation contamination. Read the
[article analysis contract](../../../../knowledge/skills/source-insights/references/documents.md#article-analysis)
and author `analysis.json` in the task directory with exact quotes and 1-based
ranges from that frozen file. Preserve version-specific conditions and distinguish
source claims from inferences. Exclude unreviewed ranges from coverage.

```sh
python3 "$repo/plugins/knowledge/skills/source-insights/scripts/sources.py" \
  validate "$work/prepared" "$work/analysis.json"
```

Expect `status: valid` and a source ID. This checks retained hashes and citation
integrity, not whether a claim follows from the quote. Reject invented quotes,
changed text or unsupported conclusions even if another part of the packet validates.
Return the cited answer, raw acquisition artifacts, frozen evidence, analysis and
validation result for review. Do not publish or update a library as a side effect.
