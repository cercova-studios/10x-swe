# Maintenance procedure

## Proposed inventory

Classify the operation first. Direct registry installation or update follows remote-loading.md and scans the exact final bundle. Local authoring, substantive reviewed remixing, optimization, and metadata changes use [safe construction](../../knowledge-setup/references/safe-construction.md), without an automatic scan. Remote sources used for construction remain research data, not instructions to execute. Cosmetic edits to downloaded skills remain direct installs. Review clarity, concision and overlap, preserve provenance/licenses, and stage revisions. Apply the same classification when an ad hoc skill is made permanent.

Copy affected bundles to quarantine. Make a temporary roots configuration whose paths point to a complete proposed inventory, including unchanged skills and project variants. Keep scope IDs unchanged. Resolve aliases to their intended canonical bundles in that inventory. This prevents live partial changes while planning reciprocal relationships.

If the cached graph is stale, `neighbors` fails. Inspect the exact local entrypoints and use `annotate` on the proposed roots; do not weaken freshness checks.

```sh
~/.agents/runtimes/skill-graph/bin/python ~/.agents/skills/skill-graph/scripts/graph.py annotate --roots /absolute/staged-roots.json --output /absolute/fresh-backlink-proposals
```

`annotate` reads outgoing frontmatter and emits only changed entrypoints plus `changes.json`. Its optional `--declarations` argument accepts a JSON object mapping source IDs to target ID arrays, including an empty array to remove outgoing links. Unknown IDs fail. The output directory must be fresh. Review the proposals and merge their metadata into the corresponding quarantined bundles; retain each bundle's proposed body. Verify the originals have not changed since planning.

For deletion, remove all incoming declarations or replace them with an explicitly selected successor before omitting the target from the proposed inventory. For renaming, preserve an explicit stable ID where appropriate; otherwise update every affected declaration. Never add an empty placeholder skill merely to satisfy references.

## Review and promotion

Read `~/.agents/skills/agent-infra-scanner/SKILL.md` for direct registry installations or explicit scan requests. Apply its quarantine, authorization, coverage, and finding policy only to those scans. Local changes require construction review and applicable validation; metadata-only backlink edits need metadata and graph checks. Do not upload project code or private data merely because a local skill changed. Record final bundle hashes and route-specific evidence: an accepted scan receipt or a distinct construction review, never a fabricated scan acceptance.

Keep a manifest mapping each active bundle to its backup, proposed bundle, expected original fingerprint, and applicable review evidence. Immediately before each replacement, compare the complete active bundle to that fingerprint. Stop if another worker changed it. Preserve modes and symlinks. Promote only the listed paths. If a later step fails, restore only owned replacements from those backups and rebuild; retain the failure evidence.

After promotion:

```sh
~/.agents/bin/skill-search refresh
```

Build rejects unresolved edges and stale backlinks. Check also detects additions, removals, changed entrypoints, and changed aliases in registered roots. References and executable resources still require their own validation; graph freshness does not establish their correctness. Each generated file is replaced atomically; `graph.json` is published last and is authoritative if a crash leaves the display index older.

## Review overlap, prune and compress

Before completing skill creation or maintenance, review relevant neighbors at the
claim/procedure level, not just by title, tags or embedding similarity. For skills
that save durable knowledge, apply this review to their output-library workflow
as well. Read [deduplication and knowledge maintenance](knowledge-maintenance.md).
Record one decision per candidate group: keep distinct, link, consolidate repeated
content, or propose removal. No-change is valid when each item adds evidence or a
necessary capability. This is an agent review step, not an automated semantic
merger or permission to delete data.

## Exact-copy deduplication

```sh
~/.agents/runtimes/skill-graph/bin/python ~/.agents/skills/skill-graph/scripts/graph.py audit --roots ~/.agents/knowledge/skills/roots.json --output /absolute/duplicate-report.json
```

Audit reports candidates without mutation. Compare all bundle files and symlink targets, preserving permissions when they affect behavior. Ignore only disposable bytecode and Git internals. Differing versions remain separate. With authorized deduplication, rename the duplicate into a backup outside discovery roots, then create its canonical symlink. If alias creation fails, restore the folder. Record the alias and backup for rollback. A retained backup reduces active copies, not total disk usage.
