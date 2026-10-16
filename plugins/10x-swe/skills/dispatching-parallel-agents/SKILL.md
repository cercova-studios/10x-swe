---
name: dispatching-parallel-agents
description: Coordinate authorized independent tasks with bounded ownership, explicit handoffs and integrated verification.
metadata:
  skill-graph-id: plugin/10x-swe/dispatching-parallel-agents
related:
  - '[[plugin/10x-swe/subagent-driven-development/SKILL]]'
  - '[[plugin/10x-swe/task-coordination-strategies/SKILL]]'
  - '[[plugin/10x-swe/parallel-debugging/SKILL]]'
---

# Dispatch independent work

Use only when delegation is authorized by the user and harness, available, and
useful. A graph relationship or this skill never grants permission to launch agents
or message another chat. Work directly when tasks share state or need ordered edits.

1. Separate genuinely independent domains; identify shared files and dependencies.
2. Assign each worker a goal, owned files, exclusions, input artifacts, completion
   checks, stop conditions and a reporting deadline. State that other workers share
   the codebase and their edits must be preserved.
3. Dispatch with the available native agent interface; do not assume a `Task` API.
   Keep dependent work sequential and exchange explicit artifacts at handoff.
4. Require observations, commands/results, changed paths, failures and unknowns.
   A sent task or a worker summary is not completion evidence.
5. Inspect the combined diff, resolve conflicts, and run the public integration
   scenario. Do not weaken tests or replace event synchronization with longer sleeps
   to make failures disappear. The coordinating agent owns final verification.

For planned dependent implementation, compare
[[plugin/10x-swe/subagent-driven-development/SKILL]]. For broader assignment models,
consult [[plugin/10x-swe/task-coordination-strategies/SKILL]] only if needed.
For competing bug hypotheses, use [[plugin/10x-swe/parallel-debugging/SKILL]].
