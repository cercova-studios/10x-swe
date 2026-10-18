---
name: find-skills
description: Find a suitable skill in the installed or bundled catalog first, then search external sources when local guidance does not cover the task. Use when users ask how to do something, request a skill, or want to extend agent capabilities.
---

# Find skills

Start with guidance the user already has. Discovering a skill does not authorize
installing it, executing its helpers, or following unreviewed remote instructions.

## 1. Identify the task

Name the domain, the concrete outcome and any constraints. Search with specific
terms such as "debug regression", "React performance" or "review test coverage".

## 2. Search locally first

If the knowledge tools are installed and activated:

```sh
skill-search search 'debug a regression' --limit 5
skill-search load plugin/10x-swe/diagnose
```

Use the exact ID returned by search; the second command shows a bundled example.
Read the selected entrypoint and only the relevant references before using it.
Local search uses the explicitly registered inventory; it does not crawl every
skill directory on the machine.

Without `skill-search`, inspect the plugin's README catalog and the harness's
available skills. If the harness does not include that README, use the
[repository catalog](https://github.com/cercova-studios/10x-swe/blob/main/plugins/10x-swe/README.md#skills).
Read the matching local `SKILL.md` directly. Engineering
skills do not require building the knowledge toolchain just to discover them.
For example, diagnosis and refactoring already have bundled workflows.

If an appropriate local skill exists, use it and stop searching. Explain a gap
only when the local guidance does not cover the requested outcome.

## 3. Search externally when needed

Prefer the knowledge tool's explicit remote discovery when available:

```sh
skill-search search 'browser automation' --remote --limit 5
```

Use public search terms. Remote search sends the query to the public skills.sh
registry; a matching description or popularity rank is not a trust assessment.
For loading or installation through this tool, read the remote review procedure at
`$AGENT_KNOWLEDGE_HOME/skills/skill-graph/references/remote-loading.md` in an activated
portable installation, or its
[repository copy](https://github.com/cercova-studios/10x-swe/blob/main/plugins/knowledge/skills/skill-graph/references/remote-loading.md):
prepare the exact bundle, obtain authorization for scanner uploads, inspect the
accepted content, then install only when requested. Missing scanner prerequisites
are a blocker for that loading route, not permission to bypass it.

As a separate discovery fallback, browse [skills.sh](https://skills.sh/) or, if Bun
is already available and running the package is authorized, use the Skills CLI:

```sh
bunx skills find react performance
```

`bunx` may download and execute the CLI. Check the current official CLI help before
using installation flags. Search metadata can inform a recommendation; do not load
remote instructions or execute downloaded helpers while merely researching options.

## 4. Recommend and review before installing

Present the relevant skill's purpose, source URL and why existing guidance is
insufficient. Identify prerequisites and whether it would affect this project or
all projects. Obtain approval for the exact source and destination before installing.
Avoid global, unattended installation as a default.

Review the full bundle, provenance, license and overlap with local skills. Keep
unreviewed material outside active skill roots. The knowledge tool's scanner-gated
route and a harness's own installation flow are different trust boundaries; never
use another installer to evade a failed review. Preserve materially different
versions and do not overwrite existing skills silently.

If no suitable skill is found, help directly with the task where possible. Offer
local skill authoring only when the user wants reusable guidance; the bundled
[create-agent-skills](../create-agent-skills/SKILL.md) guide covers that workflow.
