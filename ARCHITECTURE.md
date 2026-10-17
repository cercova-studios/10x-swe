# 10x-swe

## Boundaries

The `10x-swe` repository is a plugin marketplace. `.claude-plugin/marketplace.json`
registers the independent `10x-swe` and `knowledge` plugin directories.

`plugins/10x-swe` owns engineering guidance, specialist references and workflows.
`plugins/knowledge` owns portable discovery, evidence preparation and installation.
Each executable remains independently callable. Producers exchange explicit
versioned JSONL records and files; discovery never grants execution authority.

## Domain types

- Distribution manifest: source/version/digest/license, build inputs and capability checks.
- Installation receipt: package revision, installed artifacts and verified capabilities.
- Existing-skill inventory: bounded metadata, full-bundle digest, original location,
  aliases, conflicts and parse limitations. Existing instructions are untrusted data.
- Skill/workflow graph: explicit identities, directed routes, resource hashes and
  labeled inferred relationships. Ranking is not approval or truth.
- Evidence library: immutable source records, exact citations and reviewed analysis.
- Portable records: independent skills, sessions, insights and bookmark snapshots.

## Installation and extension points

The bootstrap plans first, installs into an explicitly owned prefix, and verifies
tools before reporting readiness. It does not edit shell profiles, global harness
instructions, credential stores, existing skills or source sessions. Optional
connectors, media extraction, local models and Dagu have separate
prerequisites; unavailable capabilities remain visible in doctor output.
Personal Kindle delivery, SSH configuration and device workflows are excluded.

Keyword `skill-search path` uses declared relationships without a neural map.
Semantic routing remains optional and validates its mapping provenance. Session
onboarding explicitly indexes the selected harness; setup leaves that index empty.
Source-insights exposes read-only evidence/analysis validation. Session review
checks citations and prepared hashes before issuing a digest, and stops without
creating a destination library or granting publication approval.

Existing skill roots are explicit. Inspection never executes their scripts or
hooks. Exact duplicate bundles can share an indexed identity; differing bundles
with the same name remain distinct. Suggested rewrites or activation require review.

Tool sources and dependency locks ship in the repository. Personal libraries,
tokens, session transcripts, bookmarks, caches and machine binaries do not.
Reviewed skill changes use staged proposals, backups and concurrent-change checks.
Source revisions install into fresh prefixes; an owned receipt never silently
upgrades an existing installation. Remote publication and delivery remain separate acts.
Completed setup retries verify readiness without requiring compilers; incomplete
installs still require the documented build prerequisites.

## Invariants

1. No existing skill, source corpus or conflicting installation is overwritten.
2. A setup failure is not readiness; a skipped capability is not a pass.
3. No implicit cloud AI, bookmark import, session crawl or evidence publication.
4. Artifact hashes bind inspection and installation; paths cannot escape ownership.
5. Discovery, provenance, review and execution authority remain separate.
6. Skills retain distinct triggers, conditions, evidence limits and upstream credit.

## Verification

Exercise a fresh isolated installation, repeat setup, interrupted/failed setup,
malformed and duplicate existing skills, changed resource hashes, portable exports,
and the session-to-reviewed-insight path. Test Linux and macOS in CI; only executed
platform checks count as verified. Keep capability-specific prerequisites explicit.

## Further reading

[Documentation](https://github.com/cercova-studios/10x-swe/wiki)
covers setup, composition and platform requirements. Executable contracts and
skill resources stay beside their source for offline use.
