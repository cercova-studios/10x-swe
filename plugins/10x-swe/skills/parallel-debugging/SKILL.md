---
name: parallel-debugging
description: Compare independent hypotheses when a reproduced failure spans multiple causes; use parallel investigators only with explicit authorization.
metadata:
  skill-graph-id: plugin/10x-swe/parallel-debugging
uses:
  - '[[plugin/10x-swe/diagnose/SKILL]]'
related:
  - '[[plugin/10x-swe/dispatching-parallel-agents/SKILL]]'
---

# Compare competing causes

Use [[plugin/10x-swe/diagnose/SKILL]] to establish a shared reproduction and evidence
contract first. Parallelism is optional. Without delegation authorization, run the
same comparisons sequentially.

Form distinct hypotheses across logic, data, state, integration, resources and
environment. Each needs a prediction, a falsifying observation and a bounded probe.
Use [[plugin/10x-swe/dispatching-parallel-agents/SKILL]] only for independent probes
with separate ownership. Investigators must not change shared state or production
instrumentation without authorization.

Collect input/artifact identity, environment, command, exit status, source anchors,
observations, counterexamples and coverage gaps. A code suspicion or correlation is
not a reproduced causal mechanism. Do not invent numeric confidence percentages.

Classify each hypothesis as supported, falsified or unresolved. Prefer a controlled
intervention that changes the reported symptom over the number of agreeing agents.
Multiple supported causes may interact; no supported cause means the investigation
continues. Integrate findings before implementing a fix; then rerun the original
reproduction and affected checks. Record what remains unverified.
