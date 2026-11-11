---
name: 10x-mode
description: Route a hard engineering task to one existing workflow. Use for a bug
  fix, refactor, feature, architecture or investigation, parallel work, or finishing
  a branch or pull request, including when the user asks for 10x-mode.
metadata:
  skill-graph-id: plugin/10x-swe/10x-mode
  skill-graph-uses: plugin/10x-swe/diagnose, plugin/10x-swe/parallel-debugging, plugin/10x-swe/test-driven-development, plugin/10x-swe/refactor, plugin/10x-swe/brainstorming, plugin/10x-swe/improve-codebase-architecture, plugin/10x-swe/code-research, plugin/10x-swe/grill-me, plugin/10x-swe/grill-with-docs, plugin/10x-swe/deep-architecture-analysis, plugin/10x-swe/dispatching-parallel-agents, plugin/10x-swe/subagent-driven-development, plugin/10x-swe/task-coordination-strategies, plugin/10x-swe/finishing-a-development-branch, plugin/10x-swe/using-git-worktrees, plugin/10x-swe/find-skills
  skill-graph-used-by: ''
uses:
- '[[plugin/10x-swe/diagnose/SKILL]]'
- '[[plugin/10x-swe/parallel-debugging/SKILL]]'
- '[[plugin/10x-swe/test-driven-development/SKILL]]'
- '[[plugin/10x-swe/refactor/SKILL]]'
- '[[plugin/10x-swe/brainstorming/SKILL]]'
- '[[plugin/10x-swe/improve-codebase-architecture/SKILL]]'
- '[[plugin/10x-swe/code-research/SKILL]]'
- '[[plugin/10x-swe/grill-me/SKILL]]'
- '[[plugin/10x-swe/grill-with-docs/SKILL]]'
- '[[plugin/10x-swe/deep-architecture-analysis/SKILL]]'
- '[[plugin/10x-swe/dispatching-parallel-agents/SKILL]]'
- '[[plugin/10x-swe/subagent-driven-development/SKILL]]'
- '[[plugin/10x-swe/task-coordination-strategies/SKILL]]'
- '[[plugin/10x-swe/finishing-a-development-branch/SKILL]]'
- '[[plugin/10x-swe/using-git-worktrees/SKILL]]'
- '[[plugin/10x-swe/find-skills/SKILL]]'
---

# 10x-mode

Pick one playbook, copy its steps into the todo list, and follow the workflow
skills those steps name. Do not restate their procedures here.

## Rules

1. Restate the goal and the smallest change that meets it before editing.
2. Follow the repository decision order: correctness, safety, observability,
   operational simplicity, maintainability, portability, performance, then elegance.
3. Verify the real outcome before calling the task done. Label each claim
   measured, inferred, or guess in the same sentence. A prediction is a guess.
   Run a check you can run instead of handing it back.
4. Destructive, secret, authentication-boundary, production, and publication
   actions need explicit authorization and a rollback. Delegation, installation,
   and network access need the same authorization. A skill link does not grant them.
5. Preserve unrelated work. Commit, push, merge, or deploy only when that step
   is authorized.
6. When the work depends on a domain under Domain references, read that skill's
   `SKILL.md` before editing and open only the sections it points at. If nothing
   listed fits, follow [[plugin/10x-swe/find-skills/SKILL]]. Discovery does not
   authorize installing or running an external skill.

## Playbooks

Copy the matched playbook's numbered steps into the todo list before any
task-specific todos. Keep a step you do not take, and write `skip:` plus the
reason on that item. Then follow the playbook.

| Task | Playbook |
|---|---|
| A bug or performance regression to reproduce and fix | [bug-fix](playbooks/bug-fix.md) opens [[plugin/10x-swe/diagnose/SKILL]], [[plugin/10x-swe/parallel-debugging/SKILL]], and [[plugin/10x-swe/test-driven-development/SKILL]] |
| A behavior-preserving structure change | [refactor](playbooks/refactor.md) opens [[plugin/10x-swe/refactor/SKILL]] and [[plugin/10x-swe/test-driven-development/SKILL]] |
| New or changed behavior | [feature](playbooks/feature.md) opens [[plugin/10x-swe/brainstorming/SKILL]], [[plugin/10x-swe/test-driven-development/SKILL]], and [[plugin/10x-swe/improve-codebase-architecture/SKILL]] |
| A question, design, or investigation without an agreed code change | [architecture](playbooks/architecture.md) opens [[plugin/10x-swe/code-research/SKILL]], [[plugin/10x-swe/improve-codebase-architecture/SKILL]], [[plugin/10x-swe/grill-me/SKILL]], [[plugin/10x-swe/grill-with-docs/SKILL]], and [[plugin/10x-swe/deep-architecture-analysis/SKILL]] |
| Two or more independent tasks, or a plan of independent tasks | [parallel](playbooks/parallel.md) opens [[plugin/10x-swe/dispatching-parallel-agents/SKILL]], [[plugin/10x-swe/subagent-driven-development/SKILL]], and [[plugin/10x-swe/task-coordination-strategies/SKILL]] |
| Implementation is done and the branch needs a merge, PR, or cleanup decision | [finish](playbooks/finish.md) opens [[plugin/10x-swe/finishing-a-development-branch/SKILL]] and [[plugin/10x-swe/using-git-worktrees/SKILL]] |

A defect found during feature or refactor work uses bug-fix for that defect.
Parallel work still follows the playbook for each task. When two playbooks fit,
do the one that produces the requested artifact, and keep the other as a later
todo if the request includes it.

## Domain references

These skills do not auto-load. Read the file. On hosts whose skill tool skips
manual-only skills, the file read is the load path.

- Python references: `python-anti-patterns`, `python-background-jobs`,
  `python-code-style`, `python-configuration`, `python-design-patterns`,
  `python-error-handling`, `python-observability`, `python-resilience`,
  `python-resource-management`, `python-type-safety`
- Python workflows that still auto-load: `async-python-patterns`,
  `python-performance-optimization`, `python-testing-patterns`
- Python packages: `uv-package-manager`
- LLM applications: `langchain-architecture`, `llm-evaluation`
- Go concurrency: `go-concurrency-patterns`
- Data and services: `sql-optimization-patterns`, `cqrs-implementation`,
  `microservices-patterns`, `error-handling-patterns`, `memory-safety-patterns`
- Interfaces and docs: `e2e-testing-patterns`, `agent-browser`, `chrome-devtools`,
  `prompt-engineering-patterns`, `architecture-decision-records`,
  `obsidian-markdown`, `bash-defensive-patterns`

Search when the name is not in this list:

```sh
skill-search search 'the task' --limit 5
```

The router shape adapts [pstack poteto-mode](https://github.com/cursor/plugins/blob/8ad8a41fe418f7c948540641cf1d8649fba99db7/pstack/skills/poteto-mode/SKILL.md)
under the [MIT license](../../LICENSE).
