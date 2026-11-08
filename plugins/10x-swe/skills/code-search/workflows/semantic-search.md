<required_reading>
Read these reference files now:
1. `references/tool-selection.md`
2. `references/zg.md`
3. `references/repo-discovery.md`
</required_reading>

<objective>
Search by concept, behavior, or intent with one ranked tool after the repository layout is understood.
</objective>

<process>
<step number="1">
Run `zg --status` at the repo root. If it reports no index, report that and fall back to ast-grep or ripgrep. Build an index only when the user authorizes it.
</step>

<step number="2">
Use repo-discovery output to anchor the search with file paths, symbols, or subsystem names when possible.
</step>

<step number="3">
Run one semantic query that describes the behavior, not just the literal identifier. With zg, put the behavior in `--vector` and any identifier guesses in repeated `--fts` groups in the same call. Add `--refresh wait` when the working tree matters and `--preview none` to locate before reading.
</step>

<step number="4">
If results are too broad, add concrete anchors such as filenames, symbols, or subsystem names, or zg filters such as `-g`, `--category code` or `--prefer-symbol`. If results are too narrow, widen the query and remove unnecessary constraints.
</step>

<step number="5">
Read the best current-source hit. If semantic search is not sufficient, fall back to ast-grep for structure or ripgrep for exact text and absence checks.
</step>
</process>

<success_criteria>
- One suitable ranked tool locates a credible current-source anchor.
- Index availability and freshness are explicit.
- The result set is usable for follow-up investigation.
</success_criteria>
