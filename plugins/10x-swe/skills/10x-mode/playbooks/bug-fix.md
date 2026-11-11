### Bug fix

1. Restate the failure, where it happens, and the smallest change that would count as fixed.
2. Read and follow [[plugin/10x-swe/diagnose/SKILL]].
3. When independent hypotheses need separate probes and delegation is authorized, read [[plugin/10x-swe/parallel-debugging/SKILL]]. Otherwise keep the probes sequential inside diagnose.
4. Read and follow [[plugin/10x-swe/test-driven-development/SKILL]] for the regression at the seam diagnose names.
5. If the work depends on a domain listed in 10x-mode, read that skill's `SKILL.md` before editing.
6. Re-run the original failure. Report the observed before and after. Name anything you could not run as unverified.
7. Stop. Switch to the finish playbook only when the user asked to integrate the branch.
