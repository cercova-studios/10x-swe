# Evaluate a skill on realistic work

Use representative tasks with explicit acceptance checks. Run bounded, reversible
workflows, inspect raw outputs and failure cases, then revise only where evidence
shows a gap. Keep test artifacts isolated from later runs.

When independent agents are authorized, pass the skill, realistic request and raw
task-local artifacts. Do not reveal expected answers, suspected bugs or proposed
fixes unless those details belong in the task. State the evaluator's role and
material constraints honestly. Leaked answers do not establish generalization.

Preserve original acceptance checks. Record observed behavior, failures and
remaining uncertainty. A graph refresh or plausible explanation does not prove
that agents follow the skill. Obtain authorization before production changes,
external exports or costly evaluations. Review and publication remain distinct.
