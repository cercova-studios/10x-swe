---
name: test-driven-development
description: Test new or changed behavior and bug fixes before implementation;
  use a passing baseline for behavior-preserving refactors. Use when implementing
  behavior, adding a regression check, or explicitly requesting TDD.
---

# Test behavior before changing it

For new or changed behavior and bug fixes, make the expected behavior executable before
implementation. For a behavior-preserving refactor, establish a relevant passing
baseline; do not invent a failing test. Preserve existing work and unrelated edits. Do
not delete implementation merely because tests came later.

1. Name the promised behavior, affected interface and real trigger. Read the existing
   tests and choose the closest check that reaches that trigger.
2. Write one focused failing test before the change. Derive its expected result from the
   requirement. Run it and verify that it fails because the behavior is missing or
   wrong, rather than a broken fixture, missing dependency or typo.
3. Apply the smallest implementation or fix. Run the new test, the original reproduction
   where applicable, and affected checks. Preserve error handling, validation and
   cleanup. Address failures without weakening acceptance criteria.
4. Refactor only while the relevant checks remain green. Report the failure before the
   change, the result after it, and unresolved gaps.

Judge a test against two changes: breaking the promised behavior should make it fail;
reorganizing internals without changing behavior should leave it passing. Observe
returns, errors, persisted state and effects through the interface that consumers use.
An external service's request can be behavior; an internal helper's invocation usually
is not. Never calculate the expected answer with the implementation being tested.

If no practical automated regression reaches the trigger, use an adequate executable
script, replay, browser scenario or documented manual reproduction. Explain what it
covers and what remains unverified. Do not treat a weak mock test as evidence, create
unrelated infrastructure to satisfy a ritual, or weaken existing checks to obtain a
pass. Necessary verification remains an obligation even when expensive.

For intermittent failures, retain the seed, trace or observed failure rate instead of
claiming a passing rerun proves the defect is gone.

When adding mocks or test utilities, read the setup and lifecycle examples in [testing
anti-patterns](testing-anti-patterns.md). Apply the observable-boundary criterion above
when judging assertions on test doubles. Understand the real dependency and preserve the
side effects the test needs; avoid test-only methods in production classes. A skipped,
blocked or incomplete check is unverified.

Selected test-quality guidance adapts [pstack](https://github.com/cursor/plugins/blob/8ad8a41fe418f7c948540641cf1d8649fba99db7/pstack/skills/principle-test-behavior-not-implementation/SKILL.md)
under the [MIT license](../../LICENSE).
