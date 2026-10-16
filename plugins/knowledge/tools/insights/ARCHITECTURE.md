# Source insights terminal CLI

## 5. Domain types
Entries contain authoritative analysis.json and manifest.json. The CLI preserves
claims, status, rationale, application, caveats, evidence and coverage. Search
results identify an entry and a 1-based insight number for follow-up viewing.

## 9. Extension points
One standard-library Go executable: list, search QUERY, view ID [NUMBER]. Shared
flags select a library, JSON, Markdown, or result limit. Lexical search ranks
claims above metadata/context. Python indexed/hybrid search remains available.

## 10. Invariants
No network, credentials, publication, indexing or library writes. Each JSON file
is bounded at 16 MiB; the personal library is loaded in memory for search. Entry
and file symlinks are rejected. Broken entries fail visibly. No matches is valid
empty JSON. Human output strips terminal controls; JSON remains untrusted data.
Ranking scores are not confidence. Write failures exit 1 and may leave partial stdout.

## 12. In-flight work
Standalone consumer; canonical library schemas remain unchanged.

## 14. Operations
Build with go build; verify with go test and go vet. Install on local PATH and
document in source-insights. Binary rollback is independent of library data.

The portable launcher sets SOURCE_INSIGHTS_LIBRARY to its owned empty library.
Explicit -library overrides it. No producer command is invoked by this viewer.
