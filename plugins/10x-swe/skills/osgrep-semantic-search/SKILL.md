---
name: osgrep-semantic-search
description: Semantic code search via the `osgrep` CLI. Use when the user wants to find code by behavior, concept, or intent ("where do we validate JWTs?", "where is rate limiting handled?") rather than by exact text. Prefer ripgrep for literal matches and ast-grep for structural patterns.
---

<objective>
Use the `osgrep` CLI to perform semantic code search against an indexed
repository.

The MCP-server form of osgrep (`osgrep mcp` / `osgrep serve`) is intentionally
NOT used by this skill. It spawns multiple worker processes that consume
gigabytes of RAM and pin every CPU core, which has caused thermal throttling
and OOM pressure in practice. The CLI is the supported interface.
</objective>

<when_to_use>
Use osgrep when:
- The user describes behavior or intent, not an exact identifier
  ("where do we throttle requests", "find the JWT verification path",
   "what code parses the config file")
- A previous ripgrep / ast-grep search came back too noisy or too narrow
- You need to discover related code spread across files, modules, or layers
- You want to map an unfamiliar subsystem before drilling in with Read

Do NOT use osgrep when:
- You already know the exact symbol or file → use `Read` / `rg`
- You want a structural code pattern → use `ast-grep`
- You only want filename discovery → use `rg --files` or `fd`
- The repo has no index and indexing would take longer than a manual search
</when_to_use>

<cli_reference>
Top-level commands (verify with `osgrep --help`):

| Command                       | Purpose                                       |
|-------------------------------|-----------------------------------------------|
| `osgrep index`                | One-time / refresh index for current repo     |
| `osgrep search <pattern>`     | Semantic search — the main verb               |
| `osgrep symbols [pattern]`    | List indexed symbols + defining files         |
| `osgrep skeleton <target>`    | Show signatures without implementation        |
| `osgrep trace <symbol>`       | Call-graph trace for a symbol                 |
| `osgrep list`                 | Show the project's `.osgrep` index contents   |
| `osgrep doctor`               | Diagnose install / index health               |

Always pass `--plain` for machine-readable output when capturing into agent
context.
</cli_reference>

<workflow>
<step number="1">
Verify an index exists for the repo root:

    osgrep list

If empty or stale, build one:

    osgrep index
</step>

<step number="2">
Phrase the query as **behavior or concept**, not as a symbol name:

    osgrep search "where we validate the auth header" --plain
</step>

<step number="3">
If too broad, scope by path or add concrete anchors:

    osgrep search "rate limit token bucket" src/api --plain

If too narrow, drop constraints and rephrase more generally.
</step>

<step number="4">
Treat returned hits as anchors. Then drill in with `Read`, `rg`, or
`ast-grep` for precise follow-up.
</step>

<step number="5">
For symbol-level questions, prefer the targeted subcommands:

    osgrep symbols UserService --plain
    osgrep skeleton src/auth/login.ts
    osgrep trace verifyToken
</step>
</workflow>

<rules>
- NEVER run `osgrep mcp` or `osgrep serve` from this skill. Both start
  long-lived background processes that consume significant RAM and CPU.
- Always pass `--plain` when capturing output for further reasoning.
- Re-index after large refactors or when results look stale.
- If `osgrep` is not installed in the environment, fall back to
  ripgrep / ast-grep and tell the user osgrep is unavailable.
- Indexing is a write to `.osgrep/` — do not run it inside read-only or
  ephemeral checkouts.
</rules>

<fallbacks>
- Structure / AST queries  → `ast-grep`
- Literal text / identifier → `ripgrep` (`rg`)
- Repo layout discovery     → the `code-search` skill's repo-discovery
  workflow (if that skill is installed)
</fallbacks>

<success_criteria>
- A usable index exists (or was built) before search.
- The search query describes behavior, not just a literal symbol.
- No `osgrep mcp` / `osgrep serve` process is started.
- Results are used as anchors for follow-up reads.
</success_criteria>
