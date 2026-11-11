### Refactor

1. Name the maintenance problem and the observable behavior that must stay the same.
2. Read and follow [[plugin/10x-swe/refactor/SKILL]].
3. Read [[plugin/10x-swe/test-driven-development/SKILL]] and use its passing baseline. Do not add a failing test that current behavior already satisfies.
4. If the work depends on a domain listed in 10x-mode, read that skill's `SKILL.md` before editing.
5. Re-run the baseline and the affected public workflow. A defect you find is a separate bug-fix.
6. Stop. Switch to the finish playbook only when the user asked to integrate the branch.
