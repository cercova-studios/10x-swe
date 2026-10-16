# Choose the smallest sufficient skill route

Graph traversal discovers candidates. The agent checks applicability and constructs the actual plan.

1. State the output and required capabilities. Include project scope, authorization, runtime constraints and completion checks.
2. Retrieve a small primary shortlist with `path TASK --semantic`, or use offline lexical discovery and the session catalog. Read the relevant entrypoints.
3. For each required capability, check whether the primary workflow covers it. Inspect its conditional `uses` routes before adding skills.
4. Search separately for uncovered capabilities. Inspect `related`, cluster memberships and cross-cluster bridge skills. Similarity can miss complementary work, so do not restrict discovery to the primary's nearest neighbors.
5. Select the smallest sufficient set. Reject redundant instructions and inapplicable project variants. Prefer accepted local skills when they cover the task; use the separate remote scan procedure for missing capabilities.
6. Order prerequisites, resolve conflicting guidance and conditional cycles, then verify the output. The graph does not authorize tools, delegation, egress or spending.

For a paper-to-animation task, the output workflow may be Manim explainers. Evidence extraction is a separate capability supplied by source-insights. Read the explainer's condition for that route; a comprehensive research workflow is unnecessary unless the task requires it. For evaluator calibration plus remote-skill acceptance, retrieve calibration and scanning independently: semantic similarity may place them in different communities.

“Optimal” means sufficient task coverage with minimal unnecessary work under the user's constraints. The tool cannot prove a globally optimal path: graph edges do not encode complete task applicability, costs, prerequisites or conflicts. Candidate steps are suggestions, not a scheduled sequence. Same-name project skills are alternatives until their scope and content justify distinct uses.

The initial twelve-task synthetic pilot put all eight expected primary skills in the semantic top five and abstained on four ordinary no-skill controls. It selected six expected primaries first and found only two of four requested extensions. These are development observations, not general calibration or successful task execution. Lexical routing performed worse. Agent verification and separate capability queries remain necessary.

The map binds entrypoint hashes, bounded text locators, extraction settings and the installed model specification. Only entrypoint text is embedded; linked reference bodies are excluded. Communities are heuristic and may reflect boilerplate or miss rare interdisciplinary relationships. New connections remain inferred until reviewed and authored with a direct body link and matching frontmatter.
