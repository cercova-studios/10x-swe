<objective>
Evaluate coding agents against observable work: correct behavior, preserved constraints,
and safe changes. Use the verification section for an individual handoff; use the
whole contract to compare or audit agents. These are engineering adaptations of
reported production experience, not universal performance guarantees.
</objective>

<quick_start>
Select representative real tasks and freeze the starting revision, requirements,
acceptance checks and budgets. Keep evaluator fixtures and release authority outside
the candidate's write scope. Compare a baseline on the same tasks and record model,
harness, tools, context and environment; changing several together evaluates the
configuration, not the causal contribution of one component.
</quick_start>

<verification>
- Require behavior evidence: build/tests plus the relevant user workflow. For generated
  apps, exercise the running app; for bug findings, request a reproducer or explicit
  evidence gap. A plausible explanation or reviewer approval does not prove correctness.
- Keep fast local checks, then use the authorized project CI/platform environment for
  checks the agent runtime cannot faithfully run. Distinguish infrastructure failure
  from product failure; unavailable verification remains unverified. Do not widen
  credentials or skip checks to obtain a pass. [Spotify, Mozilla]
- Inspect diffs for deleted tests, weakened assertions, downgraded requirements or
  unrelated changes. A green build is insufficient if acceptance changed. Use
  mechanically checkable acceptance rules for mechanically checkable rules.
  [Spotify]
</verification>

<evaluation>
- Include follow-up tasks on agent-generated code, alongside existing-code tasks;
  score preserved behavior after each change. One successful initial build does not
  measure whether later requests compound defects. [Replit]
- For reviewers, include clean changes, known defects and reverted/hotfixed changes.
  Measure false alarms and misses, split by severity, alongside cost, latency and
  timeouts. Comment acceptance and PR volume are product signals, not correctness
  labels. Repeat stochastic runs under a fixed budget; show variation and denominators.
  Never present the union of discovered findings as every defect that exists. [DoorDash]
- Use executable checks where possible. Where interpretation remains, adjudicate
  disputed labels against evidence and validate the judge against held-out adjudicated examples.
  Keep refinement separate from held-out measurement. Reassess a judge that blocks
  valid changes; neither a second model nor a human label is infallible. [DoorDash, Spotify]
- Connect offline results to authorized production comparisons and reviewed failure
  traces. Turn recurring failures into regression cases and verify that mitigations
  reduce the intended failure pattern. Agents may propose fixes and assemble evidence;
  the authorized owner retains the launch decision. [Replit, Mozilla]
</evaluation>

<success_criteria>
Report task/revision identity, unchanged acceptance, actual check outcomes, per-task
failures, severity-specific results where relevant, cost/latency, and unresolved gaps.
A passing evaluation supports only its tested scope; it does not authorize release.
</success_criteria>

<sources>
Original sources inspected in October 2026; company-reported results were not rerun.
- [Replit](https://replit.com/blog/evaluating-and-improving-agent-at-scale), June 23,
  updated June 24, 2026: ViBench, A/B testing, Telescope and human launch approval.
- [DoorDash](https://careersatdoordash.com/blog/how-we-learned-to-trust-our-ai-code-reviewer-at-doordash/),
  July 6, 2026: labels, 105-case report and severity/cost appendix. Higher overall
  recall did not imply a comparable gain in combined high/critical recall.
- [Spotify engineers' transcript](https://www.infoq.com/presentations/spotify-ai-codebase-migration-agent/):
  verification runtime, invalid judge blocks and CI feedback; video/slides not inspected.
- [Mozilla](https://hacks.mozilla.org/2026/05/behind-the-scenes-hardening-firefox/),
  May 7, 2026: reproducible test cases and triage-to-release pipeline; exploits not run.
</sources>
