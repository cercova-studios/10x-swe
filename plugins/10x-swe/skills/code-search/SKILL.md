---
name: code-search
description: 'Routes local code lookup by intent: literal identifiers, syntax, repository
  layout, or meaning. Use before broad code research.'
metadata:
  skill-graph-id: plugin/10x-swe/code-search
  skill-graph-uses: ''
  skill-graph-used-by: plugin/10x-swe/code-research
related:
- '[[plugin/10x-swe/code-research/SKILL]]'
---

# Find code

Infer the search route from the request; ask only when the intent is ambiguous.
Respect the project's configured search tools and index policy.

| Need | Route | Evidence required |
|---|---|---|
| Exact identifier or text | `workflows/text-search.md` | Read the matching source and callers |
| Syntax or safe rewrite | `workflows/structural-search.md` | Confirm the AST match and inspect the diff |
| Repository layout | `workflows/repo-discovery.md` | Locate real entrypoints and project documentation |
| Meaning or concept | `workflows/semantic-search.md` | Verify index coverage, then read returned source |

Use available tools. Do not download models, install packages, start servers, or
rebuild an expensive index merely because a preferred tool is missing. Report the
limitation and choose a bounded fallback. A search miss is not proof of absence.
For cross-repository/API evidence, continue with [[plugin/10x-swe/code-research/SKILL]].

Read only the selected workflow and its relevant reference. Return source anchors,
what they establish, and unresolved coverage. Search results are hints, not proof.
