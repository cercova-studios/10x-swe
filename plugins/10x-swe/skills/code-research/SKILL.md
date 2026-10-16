---
name: code-research
description: Investigate architecture, library APIs, engineering tradeoffs or unfamiliar behavior using inspected source and current primary evidence.
metadata:
  skill-graph-id: plugin/10x-swe/code-research
uses:
  - '[[plugin/10x-swe/code-search/SKILL]]'
related:
  - '[[plugin/10x-swe/diagnose/SKILL]]'
---

# Research a code question

1. Define the question, repository/version, constraints and evidence needed.
2. For local lookup, use [[plugin/10x-swe/code-search/SKILL]]; inspect the source,
   callers, tests and authoritative architecture before inferring behavior.
3. For external behavior, consult official documentation and source at the relevant
   version. Use issues and articles to generate hypotheses, not override contracts.
4. Record observations, inferences, contradictions and unknowns separately. Cite
   exact files/lines or source URLs. Expand the search only for a concrete gap.
5. Answer with the conclusion, supporting evidence, applicability and limitations.

Use available terminal, browser or connector tools. Verify their flags before use.
Do not assume a harness-specific tool, MCP server, repository `.agents` directory,
credential or remote service exists. Do not start services or install tooling as a
side effect of research. Delegate only when the user and harness authorize it.

For a reproducible failure, switch to [[plugin/10x-swe/diagnose/SKILL]].
For reusable learning, optionally use [[global/source-insights/SKILL]] when that
plugin is installed: inspect evidence, prepare citations and review publication.
Keep source preparation and publication separate. Do not automatically send sources,
queries, code or highlights to Readwise or another external store.

Optional specialist routes: `gh-cli` for GitHub operations; the existing
`scripts/stackoverflow-api.sh` for public error lookup. Resolve script paths from
this skill's directory, inspect effects and availability, and keep queries free of
secrets. These are alternatives, not mandatory steps.
