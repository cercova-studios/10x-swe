# Terminal agent plugins

Independent engineering skills and knowledge tools for terminal agents.
[Full guide, plans and validation](https://github.com/cercova-studios/terminal-agent-plugins/wiki) · [Architecture](ARCHITECTURE.md)

## Install

Requires Python 3.11+, Rust supporting edition 2024, Go 1.22+, a C compiler and
network access for locked dependencies. Linux also needs OpenSSL headers and
pkg-config. macOS and Linux are tested; WSL follows Linux but is untested separately.
[Native Windows needs installer work](https://github.com/cercova-studios/terminal-agent-plugins/wiki/Platforms).

```sh
git clone https://github.com/cercova-studios/terminal-agent-plugins.git
cd terminal-agent-plugins
./knowledge plan
./knowledge setup
# Activate using the exact env.sh command printed by setup.
./knowledge doctor
```

Use `--prefix /absolute/new/path` on every bootstrap command for isolation.
Setup builds skill-search, bkd, distiller and insights; installs source-insights
and session-search; and indexes bundled skills. The default keyword profile needs
no model or cloud service. It does not edit profiles/harness settings, discover
credentials, index sessions, import bookmarks or publish insights.

Retry interrupted setup with the same source. Completed retries need no compilers.
Changed sources need a fresh prefix; roll back by activating the prior prefix.
Never delete a prefix containing knowledge you want to retain.

## Intake existing skills

```sh
knowledge-intake --root codex=/absolute/path/to/existing/skills --output intake.json
# Inspect coverage, conflicts, duplicates and parse errors before indexing.
knowledge-intake --root codex=/absolute/path/to/existing/skills --index
skill-search search 'debug a regression' --limit 5
skill-search path 'capture reusable session learning'
skill-search graph
```

Intake never runs helpers or rewrites sources. Indexed bundles stay namespaced,
read-only and **unreviewed**; partial inventory exits nonzero. Review a selected
SKILL.md before loading it through your harness. Discovery grants no execution,
delegation or publication authority. Bootstrap does not configure your harness.

## Compose

Tools own separate stores and exchange explicit JSONL records/files:

```sh
skill-search export --query 'topic' --limit 5 > skills.jsonl
source-insights export > insights.jsonl
cat skills.jsonl insights.jsonl | bkd --records - search 'topic' --lexical-only --list
```

Check producer success before consuming redirected files; use `pipefail` when
streaming. For session learning, follow the bundled [session-to-insight workflow](plugins/knowledge/skills/source-insights/workflows/session-to-insight.md).
It supports shell-only execution; Dagu is optional. Explicitly select sessions,
prepare evidence, author analysis and validate citations. **Stop at review when
publication is not requested. A review digest is not approval.**

[Complete examples](https://github.com/cercova-studios/terminal-agent-plugins/wiki/Getting-started) · [Optional capabilities](plugins/knowledge/README.md) · [Engineering skills](plugins/10x-swe/README.md) · [Validation history](https://github.com/cercova-studios/terminal-agent-plugins/wiki/Validation)

Plans and detailed reports live in the wiki. Executable contracts, skill resources,
licenses and upstream credits stay with their source. Tools remain independent;
personal Kindle delivery, device configuration and SSH setup are excluded.
