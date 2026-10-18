# Knowledge tools

```sh
claude plugin marketplace add cercova-studios/10x-swe
claude plugin install knowledge@10x-swe
```

Run the repository's `knowledge plan`, `setup` and `doctor` commands. Tools build
from source into an owned prefix. Each executable and store remains independent:

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

The default profile uses keyword search, no neural model, no external AI and no
service. Neural maps/ranking require the documented pinned BGE model and local
`llama-embedding`; see `skills/source-insights/references/search.md`. They fail
visibly when unavailable. Hash-based session similarity is a heuristic.

Dagu 2.19.2 is an optional local coordinator for the bundled session-to-insight
workflow. Install it separately, verify its version and inspect the workflow before
starting it. The native human task binds approval to exact evidence and destination
hashes. Run Dagu separately when using the coordinated workflow.

EPUB needs Pandoc and an explicitly supplied cover or configured cover provider.
PDF reconstruction requires PDFium and an external model provider. macOS PDF page rendering uses PDFKit. Media needs
separate tools. Connector credentials are never copied or discovered. On Linux bkd
uses explicitly injected credentials; persistent keychain auth is macOS-only.

Distiller also exports KFX through a separately installed `epub-to-kfx` converter.

See the root README for installation, existing-skill intake and pipe examples.
