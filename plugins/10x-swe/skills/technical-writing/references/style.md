# Clear language without meaning loss

Use the project's style and established terms first. The following practices adapt
STE-inspired clarity and Google's developer-writing guidance; apply judgment.

- Prefer common words and direct verbs. Use one term for one concept; do not rotate synonyms merely for variety.
- Name the actor, object and condition. Resolve pronouns with multiple possible referents. Keep necessary articles and connecting words.
- Put one main instruction in a sentence. Aim for roughly 20 words in instructions and 25 in explanations; these are targets, not gates.
- Prefer short noun phrases and one-topic paragraphs. Use lists for parallel choices and steps, not to fragment connected explanations.
- Address the reader naturally. Use active voice when the actor matters; passive voice is reasonable when it improves accuracy or emphasis.
- Remove inflated claims, vague qualifiers and unnecessary framing. Preserve intentional product voice and contractions when they help readability.
- Use sentence-case headings, descriptive link labels, code formatting for identifiers, and clear UI-control names.

## Preserve the contract

For each rewrite, compare the original and revised actors, actions, objects,
conditions, sequence, quantity, units, scope, uncertainty and obligation.

- “May fail after a timeout” must retain uncertainty and the timeout condition.
- “Publish only after approval” must retain approval as a prerequisite.
- “Keyword search runs locally” must not become a claim that every component is offline.
- “A viewer reads the library” must not become ownership of a separate database.
- A rejected input must not become a successful or silently ignored operation.
- An unconditional rule such as preserving existing titles must not be narrowed to retries or another subset of actions.

Code, identifiers, exact quotations and external names are protected spans. Ask or
retain the original when ambiguity changes the requirement; do not guess the
meaning during a cosmetic rewrite.

Lints can find structural issues, but cannot establish faithful meaning, technical
accuracy or usability. This skill uses adapted clarity principles, not an official
ASD vocabulary check or a claim of certified ASD-STE100 compliance. Formal compliance
requires the actual applicable standard and its approved verification process.
