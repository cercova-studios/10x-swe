---
name: research-readwise-obsidian
description: Use the Readwise CLI to run relevance-first research across Reader documents and highlights, then synthesize an Obsidian-ready note with source-linked evidence and explicit confidence gaps. Use when researching topics from Readwise content for PKM workflows in Obsidian.
compatibility: Requires the Readwise CLI signed in to a Readwise Reader subscription (paid) and an Obsidian vault.
---

<objective>
Use the `readwise` CLI to run deep research on a topic by searching both Reader documents and Readwise highlights, then synthesize an Obsidian-ready research note for PKM.

Scope for this skill is intentionally narrow: search, retrieval, evidence ranking, and synthesis. It does not perform inbox triage, tagging or metadata edits, exports, or archive maintenance unless the user explicitly overrides scope.
</objective>

<quick_start>
1. Run preflight and auth checks:
```bash
command -v readwise
readwise --help
```
If authentication is missing, run `readwise login` or `readwise login-with-token <token>`.

2. Run both searches for the same query in machine-readable mode:
```bash
readwise --json reader-search-documents --query "$TOPIC" --limit 20
readwise --json readwise-search-highlights --vector-search-term "$TOPIC" --limit 30
```

3. Pull deeper context for top documents:
```bash
readwise --json reader-get-document-details --document-id "<document_id>"
readwise --json reader-get-document-highlights --document-id "<document_id>"
```

4. Produce one Obsidian note using the fixed template in `<process>`.
</quick_start>

<process>
1. Normalize the input topic into:
- one primary research question
- 3 to 6 subthemes for sectioning
- 3 to 8 query variants (synonyms, alternate phrasings, opposing terms)

2. Execute initial retrieval across both systems:
- Reader documents: `reader-search-documents`
- Readwise highlights: `readwise-search-highlights`
Use relevance-focused limits first (documents 20, highlights 30). Increase only when recall is weak.

3. Rank evidence by relevance before recency.
Score each candidate snippet with this rubric:
- `3`: directly answers the research question with specific claim or detail
- `2`: supports a subtheme with useful context
- `1`: tangential but potentially useful
- `0`: irrelevant or noise
Keep score `2-3` items first. Use recency only as a tiebreaker.

4. Enrich top evidence with source context.
For top-ranked Reader documents, fetch:
- full markdown and details (`reader-get-document-details`)
- document highlights (`reader-get-document-highlights`)
Prefer exact highlighted text over paraphrase whenever available.

5. Run refinement loops only if evidence is weak.
Weak evidence means any subtheme has fewer than 2 strong snippets (`score >= 2`) or conflicting claims without sufficient support.
Perform up to 2 refinement rounds:
- round strategy A: broaden terms (synonyms, adjacent concepts)
- round strategy B: narrow terms (specific entities, date constraints)
Stop early once evidence quality is sufficient.

6. Enforce section-level snippet caps.
For each subtheme section, include at most 5 snippets. Select highest relevance first, then maximize source diversity.

7. Resolve conflicting evidence explicitly.
When sources disagree:
- present both views
- attach source-linked evidence for each view
- explain likely reasons for disagreement (timeframe, domain, methodology, or context)

8. Produce the final fixed Obsidian note.
Use this structure exactly:

```markdown
---
title: "{{YYYY-MM-DD topic-slug}}"
created: "{{ISO-8601 datetime}}"
topic: "{{research topic}}"
source_system: "readwise-cli"
tags:
  - research
  - readwise
  - obsidian
  - pkm
---

# {{research topic}}

## Research Question
{{one-sentence question}}

## Key Findings
- {{finding 1}}
- {{finding 2}}
- {{finding 3}}

## Evidence by Theme
### {{theme 1}}
1. "{{verbatim snippet}}" — [{{source title}}]({{source url}}) _(author: {{author|unknown}}, category: {{category|unknown}}, document_id: {{document_id|n/a}}, highlight_id: {{highlight_id|n/a}})_
2. "{{verbatim snippet}}" — [{{source title}}]({{source url}}) _(author: {{author|unknown}}, category: {{category|unknown}}, document_id: {{document_id|n/a}}, highlight_id: {{highlight_id|n/a}})_

### {{theme 2}}
1. "{{verbatim snippet}}" — [{{source title}}]({{source url}}) _(author: {{author|unknown}}, category: {{category|unknown}}, document_id: {{document_id|n/a}}, highlight_id: {{highlight_id|n/a}})_

## Conflicting Evidence
- **View A:** {{claim summary}}
  Evidence: [{{source title}}]({{source url}}) _(author: {{author|unknown}}, category: {{category|unknown}}, document_id: {{document_id|n/a}}, highlight_id: {{highlight_id|n/a}})_
- **View B:** {{claim summary}}
  Evidence: [{{source title}}]({{source url}}) _(author: {{author|unknown}}, category: {{category|unknown}}, document_id: {{document_id|n/a}}, highlight_id: {{highlight_id|n/a}})_
- **Why they differ:** {{reason grounded in source context}}

## Confidence and Gaps
- **Confidence:** {{High|Medium|Low}} — {{justification}}
- **Known gaps:** {{missing or underrepresented evidence}}
- **Next queries:**
  - {{query refinement 1}}
  - {{query refinement 2}}

## Sources
- [{{source title}}]({{source url}}) — author: {{author|unknown}}, category: {{category|unknown}}, location: {{location|n/a}}, document_id: {{document_id|n/a}}, highlight_id: {{highlight_id|n/a}}
- [{{source title}}]({{source url}}) — author: {{author|unknown}}, category: {{category|unknown}}, location: {{location|n/a}}, document_id: {{document_id|n/a}}, highlight_id: {{highlight_id|n/a}}
```

9. Citation requirements are mandatory:
- citations must be markdown links to source URLs
- each citation must include Readwise metadata inline (author, category, document_id, highlight_id when available)
- if a URL is unavailable, explicitly mark `url unavailable` and keep metadata

10. Obsidian naming guidance:
- recommended note filename format: `YYYY-MM-DD topic-slug.md`
- keep slugs lowercase with hyphens
- keep note title aligned with filename stem
</process>

<success_criteria>
This skill is successful when all conditions are true:

- Searches both Reader documents and Readwise highlights for the topic.
- Uses relevance-first ranking and only uses recency as secondary ordering.
- Runs at most 2 query refinement rounds, and only when evidence is weak.
- Limits evidence to a maximum of 5 snippets per theme section.
- Produces the fixed Obsidian note structure without omitting sections.
- Includes a `Conflicting Evidence` section with both views when disagreement exists.
- Always includes a `Confidence and Gaps` section, even when confidence is high.
- Uses markdown-link citations with Readwise metadata for every evidence item.
- Stays within scope: search, retrieval, and synthesis only unless user explicitly requests broader workflows.
</success_criteria>
