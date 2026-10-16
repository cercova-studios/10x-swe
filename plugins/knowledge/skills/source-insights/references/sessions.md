# Learning from active agent sessions

Distill durable findings about AI research, AI engineering, and useful connections
from mathematics, cognitive science, philosophy, psychology, neuroscience, biology,
physics or other fields. Require a concrete implication for a future research or
engineering decision; do not accumulate impressive-sounding analogies.

Use the active conversation and artifacts actually inspected. At a meaningful
milestone, before a handoff/compaction, or when asked to remember learning, check
whether anything meets this bar. Save nothing when the session adds no durable
knowledge. This is persistent retrieval, not weight training or self-modification.
There is no background watcher or guarantee that every harness runs this workflow.

## Select and verify

1. Search existing source-insights notes for the topic. If only locating prior
   conversations, use the installed session-search skill instead. Do not crawl or
   bulk-export session stores. Existing summaries and recalled claims are leads,
   not fresh evidence. Do not claim visibility into another active agent.
2. Select a mechanism, measured result, failed hypothesis, useful constraint or
   specific cross-disciplinary application. Exclude routine task status, personal
   details, secrets and repository-specific trivia without transferable value.
3. Distinguish observed results, externally sourced claims and untested hypotheses.
   A successful command proves only its observed outcome. Agent prose is not
   independent validation; several agents repeating it are not corroboration.
4. For interdisciplinary transfer, state the original concept, proposed AI mapping,
   assumptions, where the analogy breaks, and a concrete test or falsifier. Mark
   untested connections as inference and explicitly call them hypotheses.
5. Check primary sources before attributing established scientific findings. Retain
   source URL/version/date and exact locator; if unverified, say so. When the session
   only discusses a paper, do not claim to have reviewed that paper. Use the paper
   workflow separately when actual primary evidence is available.

## Retain minimal evidence with the existing publisher

For explicit piped evidence, stage a successful producer export first:

```sh
session-search export --mode naive --agent codex --limit 1 'topic' > sessions.jsonl
# Inspect the selected session ID, roles, excerpts, redactions and coverage.
cat sessions.jsonl | python3 "$SKILL_DIR/scripts/sources.py" prepare-session \
  'session:codex:NATIVE_ID' --records - --work /absolute/new/session-work
nl -ba /absolute/new/session-work/document.md
```

The helper reads only the supplied record. It retains that exact packet plus
line-numbered evidence; source paths are inert provenance, never opened. It verifies
excerpt hashes, identities and revision pins, but cannot verify original session
bytes or authorship. Manifest extraction records preserve session/turn pins through
publication and export. Original record SHA256 pins a turn; original/indexed text and
excerpt hashes distinguish redaction. Offsets count Unicode codepoints in indexed
text. Selected public excerpts and omitted oversized records remain partial coverage.
Preparation is not publication: the review and analysis steps below still apply.

Write an isolated `session-evidence.md` containing:

- Title, capture date/time with timezone, harness and session ID when available.
  If the ID is unavailable, say so; never invent one.
- Explicit coverage: selected excerpts only, reviewed task interval, omitted context.
- Short verbatim relevant user/assistant excerpts labeled by role and turn/time
  when known. Label agent-authored paraphrases as synthesis, not verbatim evidence.
- Selected observed command/results with exit status, runtime/version and relevant
  artifact path/hash where available. Preserve only nonsensitive evidence needed to
  understand the finding. Hashes identify artifacts; they do not validate results.
- Primary-source citations and qualifiers. Clearly identify hypotheses and failures.

Redact before preparation; preparation retains the input bytes. Mark redactions and
do not use a redacted fragment to substantiate what was removed. Never copy complete
logs, hidden reasoning, credentials or unrelated conversations. Avoid writing new
global instructions into a knowledge entry. Respect no-save requests.

```sh
python3 "$SKILL_DIR/scripts/sources.py" prepare-article '/absolute/session-evidence.md' \
  --work '/absolute/new/session-work' --title 'Session learning: concise topic'
nl -ba '/absolute/session-work/document.md'
```

Read the prepared text, then author analysis.json using the article schema in
`analysis-format.md`. Add `agent-session`, relevant domain tags (for example
`ai-engineering`, `cognitive-science`) and `hypothesis` for an untested connection.
Use `source-claim` only for accurately attributed evidence; use `inference` for
synthesis or transfer. Put observation vs hypothesis, provenance, scope and failure
conditions in claim/caveats. Coverage must say this is selected session evidence,
not full-session review; line citations refer to the retained evidence document.

```sh
python3 "$SKILL_DIR/scripts/sources.py" publish '/absolute/session-work' \
  '/absolute/session-work/analysis.json'
python3 "$SKILL_DIR/scripts/sources.py" search 'distinctive topic terms'
```

Read the saved note and its evidence. Verify retrieval returns the intended insight.
New supporting/contradicting findings should link the prior note with an explanation
in caveats; do not silently overwrite it. Exact identical saves deduplicate, but
semantic duplicates still require the recall-first review. A different capture
document can create a revision even when the underlying idea is similar.

Storage remains the shared source library and SQLite index. For compatibility this
workflow uses kind=article; `agent-session` and explicit provenance distinguish it
from published articles. Add a dedicated schema only if retrieval or validation
needs cannot be expressed with these existing fields.
