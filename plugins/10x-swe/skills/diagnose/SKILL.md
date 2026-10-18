---
name: diagnose
description: Diagnose reproducible bugs and performance regressions with a bounded
  feedback loop, falsifiable hypotheses, targeted probes and regression evidence.
metadata:
  skill-graph-id: plugin/10x-swe/diagnose
  skill-graph-uses: ''
  skill-graph-used-by: plugin/10x-swe/parallel-debugging
related:
- '[[plugin/10x-swe/parallel-debugging/SKILL]]'
- '[[plugin/10x-swe/improve-codebase-architecture/SKILL]]'
---

# Diagnose

Read the relevant architecture, domain contracts and current source. Preserve
unrelated work and establish which environment reproduces the reported symptom.

1. Build the smallest repeatable signal: a failing test, CLI fixture, request,
   browser scenario, captured replay or focused harness. For intermittent bugs,
   measure the failure rate and retain the seed/trace. For performance, measure a
   baseline under stated conditions before changing code.
2. Reproduce the user's actual failure; retain its input, error and environment.
   If blocked, report what is missing and continue only with labeled hypotheses.
3. Rank plausible causes. For each, state a prediction and one discriminating
   probe. Share material assumptions without inserting an unnecessary approval gate.
4. Change one variable per probe. Prefer debugger inspection or boundary logs;
   tag temporary instrumentation. Missing observations are unknown, not passes.
5. Create a regression at the seam that reaches the real trigger. Observe it fail
   for the expected reason, apply the smallest fix, and rerun the original scenario.
   If no adequate seam exists, state that verification gap instead of a shallow pass.
6. Check affected behavior and boundaries, remove probes and explain the causal
   finding, remaining uncertainty, and rollback. Commit/deploy only if authorized.

For independent competing investigations, optionally use
[[plugin/10x-swe/parallel-debugging/SKILL]] with explicit delegation authorization.
For a structural follow-up after the fix, use
[[plugin/10x-swe/improve-codebase-architecture/SKILL]]; do not expand the fix silently.
The human-assisted fallback is `scripts/hitl-loop.template.sh`; inspect it first.
