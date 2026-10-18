---
name: distiller
description: Convert a selected URL, local HTML or stdin into provenance-preserving
  Markdown/JSON or EPUB without requiring bookmark discovery.
metadata:
  skill-graph-id: global/distiller
  skill-graph-uses: ''
  skill-graph-used-by: ''
---

# Extract a selected source

Use distiller directly for an ad hoc link; bookmark search is optional.
`distiller --stdin --base-url URL --mode json` emits article-extraction/v1 JSON with
Markdown and provenance from supplied HTML. Retain the exact original HTML snapshot
and its record for evidence handoff. URL/local JSON extraction currently uses the
legacy result shape; use the stdin route for prepared evidence. Verify options with `distiller --help`.

`distiller article.html --mode epub --cover cover.png -o article.epub` creates a
readable EPUB using Pandoc and a supplied valid cover, without cover-generation
credentials. Cloud cover generation and PDF reconstruction require explicit provider
configuration and data-sharing authorization. Bootstrap does neither. Existing
destinations and missing prerequisites fail visibly.

This package excludes personal Kindle delivery. The optional generic KFX adapter
needs an independently supplied converter and is not a portable setup capability.
Keep extraction, evidence publication and delivery separate.
