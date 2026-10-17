---
name: technical-writing
description: Writes and reviews project copy, READMEs, developer documentation, tutorials, API and CLI references, UI text, errors, and agent instructions. Use whenever creating or revising project-facing prose; grounds claims in current behavior and preserves meaning while improving clarity.
---

<objective>
Help a reader understand a product, choose an action, and complete it correctly.
Write concise, accurate prose for humans and agents. Follow project terminology,
voice and documentation policy before general style preferences.
</objective>

<quick_start>
Identify the reader, their goal, the artifact and the first useful outcome.
Inspect the current capability contract before drafting. For a small edit, revise
and check the affected sentence; for a substantial rewrite, follow the process.
Read [README guidance](references/readmes.md) for landing pages,
[developer documentation](references/developer-docs.md) for procedures/references,
and [language and fidelity](references/style.md) for wording and copy reviews.
</quick_start>

<principles>
- Lead with purpose, usefulness or the reader's next action. Define unfamiliar concepts with a concrete example.
- Use familiar words, active verbs and consistent names. State the actor when responsibility matters. Keep one topic per paragraph.
- Preserve facts, conditions, scope, uncertainty, negation and requirement strength. Keep code, flags, identifiers, paths, units, quotations and URLs exact.
- Use a fact brief as evidence, not copy to paste. Express verified scope positively instead of filling product copy with absence lists or repeated disclaimers.
- Describe implemented behavior precisely. Skills prescribe work; they do not guarantee agent outcomes. Scope local/offline, safety and performance claims to the verified capability.
- Use stricter sentence discipline for procedures, errors and agent instructions. Keep README explanations natural; preserve approved product voice in UI and marketing copy.
- Keep current capabilities, setup, contracts and operations in repo docs. Put plans, TODOs, experiments and detailed validation history in the project wiki/archive. Retain essential requirements and recovery steps with the code.
</principles>

<process>
1. **Ground.** Read the project instructions and relevant architecture. Build a compact fact brief: audience, task, current capabilities, prerequisites, exact examples and important effects. Verify uncertain commands with source/help. Keep research notes separate from the published copy.
2. **Structure.** Give the artifact one job: README orientation/first success; how-to task completion; reference exact contracts; architecture current boundaries; UI copy the user's decision or next step. Load only the relevant reference.
3. **Draft.** Write the shortest complete explanation for that reader. Put prerequisites before actions. Show a concrete useful task and its expected result where applicable. Link deeper detail instead of repeating it.
4. **Challenge.** Compare every consequential claim and example with the fact brief. Check modality, actors, conditions, errors, defaults, privacy, data ownership and approval. Check what each condition modifies; preserve unconditional constraints across all actions. Fix misleading implications as well as literal errors.
5. **Edit.** Remove repetition, vague promises, jargon, filler and development narration. Preserve necessary detail even when a sentence must be longer. Apply [language and fidelity](references/style.md).
6. **Verify.** Check links, anchors, formatting and example syntax. Run the safe representative task when authorized; syntax checks alone do not establish that a workflow works. Review changed UI copy in its actual context when practical. Report check limits outside the document.
</process>

<collaboration>
Use one agent for routine edits. For substantial rewrites, an investigator can
supply verified facts, a writer draft independently, and a different reviewer
challenge the claims before an editor combines the best parts. A fresh reader
can attempt the first task. See [review and agent roles](references/review.md).
Choose models by task needs and observed results, not fixed brand rankings.
Delegation, external model calls and publication require existing authorization;
this skill grants none of them. Share only material allowed for that destination.
</collaboration>

<success_criteria>
The intended reader can explain the purpose and find the next useful action.
Consequential claims match current behavior; requirements and examples agree.
Rewrites preserve meaning and operational safeguards. Links/examples have the
appropriate checks. Deliver the requested artifact without editorial narration;
put rationale, evidence and unresolved questions in a separate review when useful.
Source attribution and adaptation details are in [sources](references/sources.md).
</success_criteria>
