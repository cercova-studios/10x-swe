# Skill structure contract

SKILL.md starts with YAML frontmatter containing a nonempty name and a description
that states when the skill applies. Keep names stable and scope identities explicitly
when registering a graph. Metadata is discovery, never permission.

The body must expose the goal, essential constraints, minimal route, inputs/outputs,
external effects and completion evidence. Prefer plain Markdown. XML is optional;
format is not evidence of quality. Put non-negotiable safety conditions in the
entrypoint and specialist examples in references linked at the point of use.

Simple skills need no router. Complex skills may have workflows/, references/,
scripts/ and templates/ only where useful. Resolve resources from the skill's own
location. Check every relative link, avoid duplicate policy and retain upstream
credit/licenses. A workflow association describes discoverability, not execution.

Review clarity, overlap, capability scope and resource safety; test a realistic task
and a failure case. Stage changes and verify the final bytes before promotion.
