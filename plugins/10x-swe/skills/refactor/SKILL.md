---
name: refactor
description: Improve code structure while preserving observable behavior, data contracts
  and error handling through small verified changes.
metadata:
  skill-graph-id: plugin/10x-swe/refactor
  skill-graph-uses: ''
  skill-graph-used-by: ''
related:
- '[[plugin/10x-swe/improve-codebase-architecture/SKILL]]'
- '[[plugin/10x-swe/diagnose/SKILL]]'
---

# Refactor safely

Name a concrete maintenance problem and its affected callers, public interfaces,
state, configuration, exports and tests. Read the architecture and inspect the
working tree; preserve others' edits. Do not redesign code merely because a pattern
or arbitrary function-length threshold suggests it.

1. Establish the behavior to preserve and a runnable baseline. Include failure,
   cleanup, concurrency and persistence behavior where affected. If no adequate
   verification seam exists, add one or state the limitation before broad changes.
2. Try deletion, inlining or a local correction before adding an abstraction. Group
   code by the domain it owns. Reuse a pattern only when it reduces actual choices
   or makes a proven invariant easier to enforce.
3. Make one coherent change. Use syntax-aware edits for nontrivial transformations.
   Preserve validation, error detail and cleanup. Types should express constraints;
   extra wrappers, builders and interfaces need a concrete caller benefit.
4. Rerun the baseline and affected public workflows. Measure performance when the
   change affects a required resource budget. Passing unit tests alone does not
   establish unchanged external behavior.
5. Search callers, aliases, configs, fixtures, docs and prompts for the replaced
   contract. Remove stale compatibility unless explicitly required; retained
   compatibility needs an owner and removal condition.
6. Explain the improvement, evidence and remaining risk. Preserve a reversible diff
   or backup. Create branches, commits, pushes or deployments only as authorized.

For architecture-level boundary changes, use
[[plugin/10x-swe/improve-codebase-architecture/SKILL]]. For a behavior defect found
along the way, use [[plugin/10x-swe/diagnose/SKILL]] and separate its acceptance.
