# zg: hybrid indexed search

`zg` (zvec-grep) ranks code and documents by meaning and by lexical match in one
call. It indexes code with symbols, signatures and enclosing scope, and documents
by heading. Use it to find a credible anchor quickly, then read current source.

Source: <https://github.com/zvec-ai/zvec-grep>. Flags below were checked against
zvec-grep 0.3.0; run `zg --help search` if the installed version differs.

## When zg is the right rung

Use zg when `zg --status` shows an index for the workspace root and the question is:

- A behavior or concept with no known symbol.
- A concept plus naming guesses. Send them as separate query groups in one call
  instead of a series of greps.
- A definition described by its role. Add `--prefer-symbol` and, if useful,
  `--symbol-type function|class|interface|enum|module|value|alias`.
- Code only, documentation only, or both. Filter with `--category code` or
  `--category document`.
- Recently changed areas. Filter with `--modified-after <date>`.

Use a filename finder for layout, an entity-aware tool for callers, references
and impact, ast-grep for syntax, and `rg` for every occurrence or absence.

## Keep the index fresh

With the daemon stopped, zg queries in direct mode with refresh off. Files added
or edited since the last index are invisible, and the output contains
`status: possibly_stale`.

- When the task depends on the working tree, add `--refresh wait`. It updates the
  existing index for changed files before answering.
- If any result shows `status: possibly_stale`, rerun with `--refresh wait` before
  relying on the result or its ranking.

## Query patterns

```bash
zg --status
zg --refresh wait --vector "where expired tokens are rejected" \
   --fts TokenExpired --fts token_expired --limit 5 --preview none
zg --hybrid "retry with backoff" --fts RetryPolicy --fuse --limit 5
zg --prefer-symbol --symbol-type function "restore an interrupted journal"
zg "deployment rollback" --category document
zg "auth middleware" --modified-after 2026-10-01 -g '!**/fixtures/**'
```

- Positional words form one hybrid query. Repeat `--hybrid`, `--fts` or
  `--vector` for separate groups; each group is headed `-- query i/n: <text> --`.
  `--fuse` merges the groups into one ranked list.
- A single path-shaped query such as `auth.ts` looks up file names first. Use
  `--hybrid` to force a content search.
- Locate with `--preview none` (one line per hit), then read the file. Use
  `--preview detail` only when outlines and file grouping help.
- The default limit is 7 hits per group. Narrow with `-g`, `-t`/`-T` and
  `--category` before raising it.

## What zg results do not prove

- `--fts` is ranked lexical retrieval, not a filter. It returns the nearest hits
  even when no file contains the term. Confirm the identifier in the returned line.
- A ranked result set never proves absence or completeness.
- `zg --rg` runs exhaustive ripgrep without an index, but a miss prints
  `No matches.` and exits 0. For absence checks and scripts, use `rg` (exit 1 on
  no match) or check the output text.
- Symbol and scope labels come from parsing. Verify relationships in source or
  with an entity-aware tool.

## Side effects and data boundary

Run these only when the user authorizes them, never as a side effect of a lookup:

- `zg --index` creates `<root>/.zvec-grep/`, which Git reports as untracked unless
  excluded, and may download a local embedding model on first use. Adding the
  exclusion to `.git/info/exclude` or `.gitignore` is a repository change.
- `--allow-remote`, a remote model or `zg --auth` sends content to an embedding
  provider.
- `zg --index --drop` deletes the index immediately, without a prompt.
- `zg --server on` starts a persistent daemon. `zg --install` rewrites agent
  configuration.

If a zg MCP server is configured, its `zvec_grep_search` tool is the same rung.
It takes `root`, `query`, optional `fts` terms and `fuse`.

If no index exists, report that and use the next semantic rung.
