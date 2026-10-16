# Session search architecture

## Domain and entrypoints

`scripts/session_search/cli.py` exposes explicit index, search, last, show, status
and export operations. `models.py` owns SessionRecord, Turn, Hit and SearchResult.
Adapters alone read their own session stores. Consumers receive public records;
no consumer path, process or library appears in the producer.

## Recall and coverage

Codex and Claude index all supported public user, assistant and tool-result text,
without the former 24-user-turn and 32,000-character truncation. Structured hidden
reasoning and Codex analysis-channel messages are excluded. Actual response records
take precedence over duplicate event messages. Codex automatic Guardian approval
traces are excluded by `session_meta.payload.source.subagent.other=guardian`;
human conversations and other subagents remain eligible.

`turns.py` bounds a JSONL record to 16 MiB and a decoded public turn to 4 MiB.
Oversized records/turns are omitted with line-specific coverage limitations. Binary
line reads remain bounded while consuming oversized records. Complete malformed
records fail the adapter; an unfinished final JSON record from an active writer is
ignored. Coverage is selected supported public text, never a full-session review.
Other adapters retain their existing metadata/body extraction. They cannot export
exact turn evidence until they implement the same Turn contract.

FTS5 BM25 now sees the retained public text. Semantic retrieval still uses local
summary embeddings (hash-ngram by default), and ontology cards remain heuristic.
This change does not establish neural paraphrase quality or ranking calibration.

## Provenance and exports

Every Turn retains native session ID through its SessionRecord, exact source path,
one-based JSONL line, JSON pointer, recorded role/timestamp, original record SHA256,
original decoded public-text SHA256 and a redaction flag. Record hashes cover the
UTF-8 JSON line without its trailing CR/LF. Exported excerpt offsets are Unicode
codepoints in the redacted indexed text; whitespace is preserved. Full indexed-text
and excerpt SHA256 accompany each citation. Known credential patterns are redacted;
this is not a complete sensitive-data detector. Inspect excerpts before sharing.

`records.py` emits one `knowledge-snapshot/v1`, corpus `sessions`, with session
and session_turn nodes, recorded part_of edges, revisions and exact-query ranks.
Session IDs are `session:AGENT:NATIVE_ID`; turns are `turn:AGENT:NATIVE_ID:LINE`.
Turn versions pin the original record SHA256, including its role and timestamp;
session revisions pin all retained turns and coverage omissions. At most 20 hits,
three 2,000-character excerpts per hit and a 16 MiB packet are permitted. A selected
hit without exact literal-matching turn provenance fails, rather than fabricating
a locator from a metadata/semantic match. No-hit or failed export emits no packet.

## Storage and failure behavior

`store.py` owns a derived SQLite index. Existing indexes gain turns_json and
limitations_json columns; refreshing a selected adapter replaces its rows, FTS,
embeddings and cards in one transaction. An enrichment failure retains the previous
complete generation. Adapter errors also preserve the last successful index timestamp.
Source stores remain unchanged. Search never implicitly crawls;
operators explicitly index stale/empty caches. Last-modified recency is not a turn
timestamp. Scope-specific index operations do not refresh other adapters.

## Composition and verification

Explicit exports can feed any validating consumer. Source-insights preparation
retains selected evidence, followed by manual interpretation and line-cited
publication. BookmarkDrop accepts explicit snapshots for combined retrieval and
navigation. These are external shell recipes, not producer dependencies. Data,
hashes, relationships and recalled assistant statements grant no execution or
publication authority.

`python3 tests/check.py` covers late-user/assistant/tool recall, hidden reasoning,
redaction, exact locators/hashes, duplicate suppression, malformed/oversized records,
Guardian filtering, SQLite rollback and failure-atomic JSONL export. Back up the
derived SQLite index before installation/refresh. Rollback restores owned skill
files and that backup, then rebuilds the skill graph; never edit source sessions.

## External workflow discovery
The skill links to source-insights/workflows/session-to-insight.md. Dagu can
coordinate its existing v1 export with preparation and reviewed publication.
Session-search gains no publisher, Dagu or orchestration-state dependency.

Explicit export --role user|assistant|tool filters selected public excerpts without
changing session ranking, stored turns, revision pins or default recall. Filtered
coverage is retained. No matching exact-role evidence fails with no partial packet.
