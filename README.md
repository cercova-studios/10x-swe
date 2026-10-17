# 10x-swe

**Engineering workflows and searchable knowledge for your coding agent.**

10x-swe is a plugin marketplace for terminal agents. Its skills are task-specific
guides your agent reads: how to investigate a bug, refactor safely, or review a
change. Its knowledge tools help you find and reuse material from skills, past
sessions, bookmarks and articles.

Use it to:

- **Investigate and fix code:** follow workflows for reproduction, diagnosis, small changes and verification.
- **Find prior work:** search skills and sessions, then explore related skills and workflows in a terminal graph.
- **Keep useful lessons:** extract reading material, prepare cited insights, review them and save them for later retrieval.

## Start with a plugin

| Plugin | Choose it for |
|---|---|
| [10x-swe](plugins/10x-swe) | Engineering skills for research, debugging, review, testing and refactoring. **Start here.** |
| [knowledge](plugins/knowledge) | Skill discovery, session recall, bookmark search, article conversion and reviewed insights. |

Install either or both in Claude Code:

```sh
claude plugin marketplace add cercova-studios/10x-swe
claude plugin install 10x-swe@10x-swe
claude plugin install knowledge@10x-swe   # optional
```

Start a new session and give the agent a concrete task:

> Use the diagnose skill: `npm test` started failing on `parser.spec.ts` after
> yesterday's merge. Reproduce the failure, identify the cause, and verify the fix.

The skill guides the investigation; the agent still needs to execute and check
its work. Other agent harnesses can load the repository's `SKILL.md` bundles
through their own skill mechanism.

## Add the knowledge tools

The knowledge plugin provides skills; build its CLI tools separately.

Requires macOS or Linux/WSL, Python 3.11+, Rust supporting edition 2024, Go 1.22+,
a C compiler and network access. Linux also needs OpenSSL headers and pkg-config.
The default keyword search runs locally. [Platform requirements](https://github.com/cercova-studios/10x-swe/wiki/Platforms).

```sh
git clone https://github.com/cercova-studios/10x-swe.git
cd 10x-swe
./knowledge plan
./knowledge setup
# Run the env.sh activation command printed by setup.
./knowledge doctor
```

Setup installs tools and indexes bundled skills. Use `--prefix /absolute/new/path`
for isolation; changed package sources require a fresh prefix.
[Setup and recovery](https://github.com/cercova-studios/10x-swe/wiki/Getting-started).

### Find skills and bring your own

```sh
skill-search search 'debug a regression' --limit 5
skill-search path 'capture reusable session learning'
skill-search graph

knowledge-intake --root codex=/absolute/path/to/skills --output intake.json
# Review the report before registering existing skills for discovery.
knowledge-intake --root codex=/absolute/path/to/skills --index
```

Intake reports duplicates and conflicts while preserving source bundles.
Indexed skills remain unreviewed; inspect them before loading their instructions.

### Connect the tools with pipes

Each tool works independently. Combine exported records without coupling their
storage implementations:

```sh
skill-search export --query 'topic' --limit 5 > skills.jsonl
source-insights export > insights.jsonl
cat skills.jsonl insights.jsonl | bkd --records - search 'topic' --lexical-only --list
```

Check each export succeeds before consuming its file; use `pipefail` when streaming.
For [session to insight](plugins/knowledge/skills/source-insights/workflows/session-to-insight.md),
select a session, prepare evidence, write an analysis, review it and publish with
approval. Dagu can optionally coordinate the same shell workflow.

## Explore further

[Guides and examples](https://github.com/cercova-studios/10x-swe/wiki) · [Tool capabilities](plugins/knowledge/README.md) · [Skill catalog](plugins/10x-swe/README.md) · [Architecture](ARCHITECTURE.md) · [Help and issues](https://github.com/cercova-studios/10x-swe/issues)

Maintained by [Rohit Nair](https://github.com/rnair98). [MIT licensed](LICENSE);
bundled tools and skills retain their upstream licenses and credits.
