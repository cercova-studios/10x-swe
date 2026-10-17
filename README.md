# 10x-swe

**Give your coding agent reusable engineering workflows and a searchable knowledge library.**

10x-swe is a plugin marketplace for terminal agents. It combines task-specific
engineering skills with tools for finding and reusing what you've already learned
from code, agent sessions, bookmarks and articles.

## What can I do with it?

| When you want to… | Use 10x-swe to… |
|---|---|
| Fix a bug or refactor unfamiliar code | Give your agent a workflow for investigation, small changes and verification. |
| Find a previous decision or useful technique | Search skills and past sessions; explore related skills and workflows in a graph. |
| Reuse something learned during a task or while reading | Extract source material, prepare a cited insight, review it and save it for later retrieval. |

Install either plugin, or use both:

| Plugin | What you get |
|---|---|
| [10x-swe](plugins/10x-swe) | Engineering skills for code research, debugging, review, testing, refactoring and specialist tasks. |
| [knowledge](plugins/knowledge) | Skill and workflow discovery, session recall, bookmark search, article conversion and reviewed insights. |

Skills guide the agent's work. The knowledge tools provide searchable material;
you choose what to index and save. Each tool also works on its own and can exchange
records through files or pipes. The default search runs locally without a model or cloud service.

## Start with engineering skills

In Claude Code:

```sh
claude plugin marketplace add cercova-studios/10x-swe
claude plugin install 10x-swe@10x-swe
```

Start a new session and ask for a specific skill, for example:

> Use the diagnose skill to investigate this regression. Reproduce it, identify
> the cause, and verify the fix.

For the knowledge skills, also install `knowledge@10x-swe` and build the CLI tools
below. Other agents can load the repository's `SKILL.md` bundles through their
own skill mechanism; bootstrap does not configure your harness.

## Add the knowledge tools

Requires macOS or Linux/WSL, Python 3.11+, Rust supporting edition 2024, Go 1.22+,
a C compiler and network access. Linux also needs OpenSSL headers and pkg-config.
See [platform requirements](https://github.com/cercova-studios/10x-swe/wiki/Platforms).

```sh
git clone https://github.com/cercova-studios/10x-swe.git
cd 10x-swe
./knowledge plan
./knowledge setup
# Run the env.sh activation command printed by setup.
./knowledge doctor
```

Setup installs the tools and indexes bundled skills. It leaves your existing
skills, harness configuration and source collections alone. Use
`--prefix /absolute/new/path` for an isolated installation; changed package sources
require a fresh prefix. [Setup and recovery details](https://github.com/cercova-studios/10x-swe/wiki/Getting-started).

Find a skill for your next task, or browse its relationships:

```sh
skill-search search 'debug a regression' --limit 5
skill-search path 'capture reusable session learning'
skill-search graph
```

### Bring your existing skills

```sh
knowledge-intake --root codex=/absolute/path/to/skills --output intake.json
# Review the report, then register the skills for discovery.
knowledge-intake --root codex=/absolute/path/to/skills --index
```

Intake reports duplicates and conflicts without rewriting bundles or running their
helpers. Indexed skills remain unreviewed; inspect a skill before loading it.

### Connect the tools with pipes

Search across skill and insight exports without sharing their databases:

```sh
skill-search export --query 'topic' --limit 5 > skills.jsonl
source-insights export > insights.jsonl
cat skills.jsonl insights.jsonl | bkd --records - search 'topic' --lexical-only --list
```

Check each export succeeds before consuming its file; use `pipefail` when streaming.
For a complete learning workflow, follow [session to insight](plugins/knowledge/skills/source-insights/workflows/session-to-insight.md):
select a session, prepare evidence, write an analysis, review it, then publish only
with approval. Dagu is optional; the same workflow runs through the shell.

## Explore further

[Guides and examples](https://github.com/cercova-studios/10x-swe/wiki) · [Tool capabilities](plugins/knowledge/README.md) · [Skill catalog](plugins/10x-swe/README.md) · [Architecture](ARCHITECTURE.md) · [Help and issues](https://github.com/cercova-studios/10x-swe/issues)

Maintained by [Rohit Nair](https://github.com/rnair98). [MIT licensed](LICENSE);
bundled tools and skills retain their upstream licenses and credits.
