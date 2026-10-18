---
name: source-insights
description: Prepare inspected source evidence, preserve exact citations, and publish
  reviewed insights into an explicit local library.
metadata:
  skill-graph-id: global/source-insights
  skill-graph-workflows: global/source-insights/workflows/session-to-insight
  skill-graph-uses: ''
  skill-graph-used-by: ''
---

# Preserve source learning

The agent reasons about evidence. `source-insights` prepares material and validates
citations; it does not independently verify claims. Search first with
`source-insights search 'topic' --limit 5`; inspect coverage, dates and caveats.
The bootstrap uses keyword FTS5; neural retrieval is an explicit optional profile.

Read only the relevant route: `references/documents.md` for articles/PDFs,
`references/video.md` for media, and [session-to-insight](workflows/session-to-insight.md)
for selected session turns. Inspect `source-insights --help` and prepared manifests
for the current analysis/citation contract. Native media dependencies are optional.

A prepared article-extraction/v1 JSON record from distiller can be passed to
`source-insights prepare-article URL --prepared FILE --snapshot ORIGINAL_HTML --work NEW_DIR`.
The HTML must be the exact input snapshot bound by the extraction hash. Selected session packets use
`prepare-session EXACT_ID --records FILE --work NEW_DIR`; neither producer is required
by the consumer. Retain snapshots, exact evidence ranges and provenance.

Author analysis and run `source-insights validate WORK ANALYSIS` to check citations,
coverage and prepared hashes without publication or a search runtime. The session
recipe's `review` operation runs that check before issuing a digest. For review-only
tasks, return the packet and stop; a digest does not authorize publication.
Inspect claims/citations/coverage and review the destination before
`source-insights publish WORK ANALYSIS --library DESTINATION`. Publication is separate
from preparation and never updates skills automatically. Session workflow approval
is bound to artifact and destination hashes; edited evidence invalidates approval.
Dagu 2.19.2 is an optional local runner; discovering a workflow does not execute it.

`source-insights export` emits knowledge-snapshot/v1 JSONL. `insights` is a separate
read-only human viewer. No source crawling, publication or cloud calls during setup.
