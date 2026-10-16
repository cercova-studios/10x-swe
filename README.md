# Terminal agent plugins

Independent engineering skills and knowledge tools for terminal agents. Start
with [ARCHITECTURE.md](ARCHITECTURE.md); this repository is source, not a personal
knowledge backup. Existing skills and stores are never overwritten by setup.

## Bootstrap a fresh environment

Requires macOS or Linux/WSL, Python 3.11+, a Rust toolchain supporting edition 2024,
Go 1.22+, and a C compiler. Linux also needs OpenSSL development headers and
pkg-config. Network access is needed to download hash-locked build dependencies.
Native Windows is unsupported. No cloud service or model is required for the
default keyword profile.

```sh
git clone https://github.com/cercova-studios/terminal-agent-plugins.git
cd terminal-agent-plugins
./knowledge plan
./knowledge setup
```

Setup prints the explicit `env.sh` activation command. It builds skill-search, bkd,
distiller and insights; installs locked Python dependencies for source-insights and
session-search; and indexes the bundled knowledge/engineering skills. It creates
empty local libraries and a receipt. It does not edit profiles/global instructions,
index sessions, import bookmarks, publish insights, discover credentials or make AI
requests. `./knowledge doctor` checks artifacts, tool entrypoints and graph freshness.
Use `--prefix /absolute/new/path` on every command for an isolated environment.

Interrupted setup retains diagnostic/build state and can be retried with the same
source bytes. A completed prefix with changed source bytes requires a fresh prefix;
upgrades never replace an installation silently. Roll back by activating the prior
prefix. Never delete a prefix containing knowledge you want to retain.

## Discover and process existing skills

```sh
knowledge-intake --root codex=/absolute/path/to/existing/skills --output intake.json
# Review conflicts, duplicates, coverage and parse limitations, then explicitly index:
knowledge-intake --root codex=/absolute/path/to/existing/skills --index
skill-search search 'debug a regression' --limit 5
skill-search path 'capture reusable session learning'
skill-search graph
```

Intake reads bounded metadata/resources and hashes complete bundles. It never runs
helpers, rewrites sources or activates instructions. Exact duplicates are identified;
same-name differing versions remain separate. `--index` registers complete bundles
as namespaced, read-only, **unreviewed** graph nodes. Unresolved/ambiguous original
links are reported in node metadata. Partial inventory exits nonzero. Resolve parse
issues or inspect narrower roots; do not interpret omitted bundles as accepted.

The CLI is harness-independent. Load a selected SKILL.md using the agent's normal
skill mechanism; review existing untrusted skills before treating them as
instructions. Registering graph data does not install a harness plugin or grant
permission. Native Claude plugin metadata is available for `10x-swe` and `knowledge`;
other harnesses can load these standard skill directories explicitly. Bootstrap
does not change their configuration or invent activation paths.

## Compose tools

```sh
# Ad hoc article extraction works without bookmarks.
distiller --stdin --base-url https://example.org/article --mode json < article.html > article.json
source-insights prepare-article https://example.org/article --prepared article.json --snapshot article.html --work /absolute/new/evidence

# Select session evidence explicitly; inspect the exact returned ID and coverage.
session-search export --mode naive --agent codex --role assistant --limit 1 'topic' > selected.jsonl
source-insights prepare-session session:codex:EXACT_ID --records selected.jsonl --work /absolute/new/session-evidence

# Join portable exports; each producer keeps its own store and ranking.
skill-search export --query 'topic' --limit 5 > skills.jsonl
source-insights export > insights.jsonl
cat skills.jsonl insights.jsonl | bkd --records - search 'topic' --lexical-only --list
```

Run producer commands successfully before consuming redirected files; use the
shell's `pipefail` when streaming. Preparation is not publication. Inspect evidence,
author analysis and explicitly review claims/citations/destination before publish.
The bundled Dagu session-to-insight workflow adds a digest-bound human review gate;
Dagu remains optional and external to the tools.

Optional local neural models, connectors, media tools and EPUB/PDF prerequisites
are described in [the knowledge plugin](plugins/knowledge/README.md). Personal
Kindle delivery and device configuration are intentionally excluded.

## Engineering skills

`10x-swe` retains specialist guidance while tightening the common research,
search, diagnosis, parallel-work and refactor routes. Relationships are conditional
discovery hints. They grant no delegation, external-message or execution authority.
See [the refresh report](docs/reports/10x-swe-refresh.json) and preserve upstream
credits in each bundle. Optional MCP configuration is an example, never part of
the source bootstrap.

Validation commands and actual platform results belong in `docs/reports/acceptance.md`.
