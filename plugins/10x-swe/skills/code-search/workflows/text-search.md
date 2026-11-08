<required_reading>
Read this reference file now:
1. `references/tool-selection.md`
</required_reading>

<objective>
Use ripgrep for exact text, literal identifiers, and lightweight fallback searches.
</objective>

<process>
<step number="1">
Choose focused patterns and constrain the search with file globs whenever possible.
</step>

<step number="2">
Use surrounding context only as needed to confirm the match.
</step>

<step number="3">
For an absence claim or a script, use `rg`: it exits 1 when nothing matches. Managed `zg --rg` searches exhaustively too, but prints `No matches.` and exits 0, so check its output instead of its exit status. Ranked `zg --fts` never proves absence.
</step>

<step number="4">
If the result set is noisy, tighten the pattern, switch to ast-grep for structure, or use zg for meaning.
</step>
</process>

<success_criteria>
- The search is fast and specific.
- Exact matches are found without unnecessary tooling overhead.
- The assistant knows when to escalate to a deeper workflow.
</success_criteria>
