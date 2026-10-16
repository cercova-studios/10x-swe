# Reproducible knowledge ecosystem and 10x-swe refresh

| ID | Deliverable | Depends on | Files | Done when |
|---|---|---|---|---|
| K1 | Inventory and provenance | — | plugins/knowledge/distribution.json, docs/reports | Sources, locks, licenses, platform limits and 10x-swe overlap decisions are explicit; no personal data ships |
| K2 | Portable standalone tools | K1 | plugins/knowledge/tools, skills | Existing graph, sessions, insights, bookmarks and extraction sources build without this Mac's paths; pipes retain evidence contracts |
| K3 | Bootstrap, doctor, existing-skill intake | K2 | knowledge, plugins/knowledge/bootstrap.py, tests | Fresh setup and retries work in an owned prefix; external skills remain unchanged; malformed/duplicate/conflicting bundles are reported |
| K4 | Tighter engineering plugin | K1,K3 | plugins/10x-swe/skills, workflows, README | Reviewed overlaps are consolidated or linked; hot entrypoints are smaller; distinct capabilities, safety conditions and provenance remain reachable |
| K5 | Acceptance and documentation | K2,K3,K4 | README.md, .github/workflows, tests, docs/reports | Clean-room setup, discovery/graph, public-record pipes and explicit publication review pass; skipped optional capabilities are reported |

Keep all changes in the isolated clone. Preserve the pre-existing local checkout.
Do not push or publish until requested. Avoid a framework or a new knowledge store;
bootstrap the independent tools already implemented and reuse their protocols.

## Completion

K1–K4 are implemented; K5's local macOS acceptance passed. Linux/macOS CI is
defined and remains unexecuted remotely. See `../reports/acceptance.md` for exact
checks, the initial failures and remaining optional/platform limits. The seven
core-route cleanup retains specialist bundles and removes the retired ambient
directory/credential-wrapper assumptions. Kindle delivery stays excluded.
