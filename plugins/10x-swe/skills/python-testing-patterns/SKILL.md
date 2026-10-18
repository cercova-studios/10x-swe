---
name: python-testing-patterns
description: Implement comprehensive testing strategies with pytest, fixtures, mocking,
  and test-driven development. Use when writing Python tests, setting up test suites,
  or implementing testing best practices.
metadata:
  skill-graph-id: plugin/10x-swe/python-testing-patterns
  skill-graph-uses: ''
  skill-graph-used-by: ''
---

# Python Testing Patterns

Use this skill to test Python behavior with pytest, fixtures, mocks, and property-based tests. Follow the project's test commands, supported Python versions, and configuration.

## Workflow

1. Read the behavior contract and nearby tests. Identify the regression, boundary, or integration risk the test must detect.
2. Select the smallest useful level: unit tests for isolated behavior; integration tests for component contracts; end-to-end tests for complete user flows.
3. Arrange explicit inputs, execute the behavior, and assert observable outcomes. Cover relevant edge cases and failures. Several assertions may describe one behavior; do not split them merely to meet an assertion count.
4. Isolate state with fixtures, `tmp_path`, and environment overrides. Use teardown even when the test fails. Scope shared fixtures carefully; avoid hidden dependencies between tests.
5. Mock external boundaries rather than the implementation being tested. Patch where the dependency is looked up. Verify real integrations separately when mocks cannot establish the contract.
6. Run the focused tests, then required project checks. Report actual commands and results, including skipped tests and unavailable services. Coverage identifies gaps; it does not establish correctness.

## Choose a reference

Open only the relevant section of [detailed patterns](references/patterns.md):

- Fundamental Patterns: pytest, fixtures, parameterization, mocking, and exceptions.
- Advanced Patterns: async tests, monkeypatch, temporary files, shared fixtures, and Hypothesis.
- Testing Best Practices: naming, retry limits, time control, markers, and coverage.
- Testing Database Code: sessions, queries, and constraints.
- CI/CD Integration and Configuration Files: suite configuration and CI examples.

The preserved examples are not production-ready templates. In particular, the email validator contradicts one test case; async fixture behavior depends on pytest-asyncio mode; database sessions need failure-safe teardown. Verify installed plugin behavior and current CI action versions before adaptation.

## Acceptance

A useful test fails when its target behavior breaks, passes with the correction, and does not depend on unrelated machine state. Never weaken assertions, hide a failure with a skip, or exclude coverage solely to obtain a passing result. Do not install plugins or contact external services merely because an example does so.
