# Knowledge tools

Search bundled skills, recall explicitly indexed sessions and turn selected sources
into reviewed, reusable insights.

## Setup and first search

For Claude Code instructions, add the marketplace and install the plugin:

```sh
claude plugin marketplace add cercova-studios/10x-swe
claude plugin install knowledge@10x-swe
```

This installs guidance, not the CLI binaries. Follow the root
[knowledge CLI setup](../../README.md#knowledge-cli-tools) for prerequisites,
`knowledge plan`, `setup`, activation and `doctor`. The plugin install defaults to
user scope; use `--scope local` for only the current repository. See the root
[Claude Code guidance](../../README.md#engineering-skills-only) for version and
activation checks.
For Codex, Grok Build, Copilot CLI, opencode and pi, see
[other agents](../../README.md#other-agents).

After activating the printed `env.sh`:

```sh
skill-search search 'debug a regression' --limit 5
skill-search load plugin/10x-swe/diagnose
```

Read the returned instructions and ask your agent to apply them to a concrete
failure. For another result, copy its exact ID from search. See the
[first diagnosis exercise](../../examples/diagnose/README.md) for a small local task.

## Commands and capabilities

Tools build from source into an owned prefix. Each executable and store remains independent:

| Command | Owns | Handoff |
|---|---|---|
| skill-search | Explicit skill/workflow inventory and lexical catalog | knowledge-snapshot/v2 |
| session-search | Derived index of explicitly selected session stores | knowledge-snapshot/v1 with exact turns |
| distiller | Selected article extraction/conversion | article-extraction/v1 and files |
| source-insights | Immutable inspected evidence and reviewed learning | knowledge-snapshot/v1 |
| insights | Read-only human view of an insights library | JSON/Markdown |
| bkd | Bookmark cache, retrieval and reviewed imports | Explicit snapshots/files |
| knowledge-intake | Bounded read-only existing-skill inventory | existing-skills/v1 |

`AGENT_KNOWLEDGE_HOME` locates installation resources. Source insights, sessions
and bookmarks accept their own explicit library/index/home overrides. Tools do not
open each other's private databases. Skill graph and insights share a stateless
pinned-model invocation primitive; neither imports the other's storage layer.

Portable setup creates keyword indexes for skill discovery and source-insights,
without downloading a neural model or starting a service. For `bkd search`, pass
`--lexical-only` when using this setup without a model; bkd's native default ranking
can require BGE when bookmarks are present. Neural maps/ranking require the documented pinned BGE model and local
`llama-embedding`; see [local search operations](skills/source-insights/references/search.md). They fail
visibly when unavailable. Hash-based session similarity is a heuristic.

Dagu 2.19.2 is an optional local coordinator for the bundled session-to-insight
workflow. Install it separately, verify its version and inspect the workflow before
starting it. The native human task binds approval to exact evidence and destination
hashes. Run Dagu separately when using the coordinated workflow.

The [newsletter recipe](skills/newsletter/workflows/daily-newsletter.md) creates a
local HTML reading room and Markdown editions from bounded public research. Its
daily Dagu schedule includes separate editorial review and seven-day retention.
The supplied adapter pairs Claude copywriting with independent Codex review.
Configure provider credentials and editorial CLIs independently.

EPUB needs Pandoc 3.12.1 (the CI-pinned version) and an explicitly supplied cover or
configured cover provider. Older Pandoc releases may lack the required CLI options.
PDF reconstruction requires PDFium and an external model provider. macOS PDF page rendering uses PDFKit. Media needs
separate tools. Connector credentials are never copied or discovered. On Linux bkd
uses explicitly injected credentials; persistent keychain auth is macOS-only.

Distiller also exports KFX through a separately installed `epub-to-kfx` converter.

See the root README for installation, existing-skill intake and pipe examples.
