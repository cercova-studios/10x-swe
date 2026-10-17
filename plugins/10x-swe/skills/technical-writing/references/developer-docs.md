# Write developer documentation

Choose the reader's job before the format.

| Artifact | Include |
|---|---|
| How-to | Goal, environment, prerequisites, ordered actions, expected result and recovery |
| Tutorial | One learning goal, a runnable example, explanations at decision points and a working result |
| CLI/API reference | Exact syntax, types, required/optional inputs, defaults, outputs, errors and side effects |
| Architecture | Current responsibilities, dependency direction, domain types, data flow and invariants |
| UI or error copy | What happened, the relevant consequence and the next useful action |

State where an action runs before the action. Put conditions and prerequisites
first. Use numbered steps for sequences and separate actions where a reader must
make distinct decisions. Prefer one supported path; link alternatives when needed.
Explain placeholders, units and expected outputs. Label illustrative output as an
example; never fabricate an observed test result.

Keep command tokens and API identifiers exact. Use fenced code with a language
label; keep prompts/output separate so copy-paste is usable. Show complete relevant
examples without real credentials. Include idempotency, concurrency or rollback
when they affect the user's task. Warn immediately before a consequential action,
without burying the instruction in an unrelated checklist.

Use descriptive links and headings, accessible names for controls, meaningful
image alternatives and keyboard-accessible instructions. Do not rely only on
color, position or a screenshot. Explain diagrams in surrounding text.

For UI/product copy, respect the product voice and available space. Use concrete
labels and recoverable errors. Do not force controlled-language vocabulary on
creative copy. A short message must still preserve the relevant condition and
next action. Review it in the actual UI rather than as isolated sentences.
