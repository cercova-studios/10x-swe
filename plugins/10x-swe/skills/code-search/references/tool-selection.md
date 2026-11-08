<objective>
Choose the lightest search tool that still answers the question.
</objective>

<tool_map>
<row>
<task>Know the repo layout</task>
<tool>fff-mcp if available, otherwise rg --files and glob</tool>
</row>
<row>
<task>Search by meaning or intent</task>
<tool>zg</tool>
</row>
<row>
<task>Check a concept and several naming guesses at once, or find a definition by its role</task>
<tool>zg with separate `--vector`/`--fts` query groups, or `--prefer-symbol`</tool>
</row>
<row>
<task>Find callers, callees, impact, or how an area connects</task>
<tool>codegraph when the repository has a codegraph index</tool>
</row>
<row>
<task>Search by structure or syntax</task>
<tool>ast-grep</tool>
</row>
<row>
<task>Search for exact text or identifiers</task>
<tool>ripgrep</tool>
</row>
</tool_map>

<rules>
- Start with repo discovery when the shape of the codebase is unclear.
- Use one ranked semantic tool once the repo is anchored; do not repeat the same query in every index.
- When `zg --status` shows an index for the root, zg is that tool. Add `--refresh wait` when the working tree matters. See `references/zg.md`.
- Move from a found symbol to codegraph for relationships. Run `codegraph status` first and `codegraph sync` if relevant changes are pending. See `references/codegraph.md`.
- Use ast-grep when syntax matters more than wording.
- Use ripgrep when the literal text is already known, and for every absence claim.
- Escalate only when the current tool cannot answer the question well.
</rules>
