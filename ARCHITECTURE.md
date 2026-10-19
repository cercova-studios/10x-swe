# 10x-swe

## Boundaries

The `10x-swe` repository is a plugin marketplace. `.claude-plugin/marketplace.json`
registers the independent `10x-swe` and `knowledge` plugin directories.

`plugins/10x-swe` owns engineering guidance, specialist references and workflows.
`plugins/knowledge` owns portable discovery, evidence preparation and installation.
Each executable remains independently callable. Producers exchange explicit
versioned JSONL records and files; discovery never grants execution authority.

`playground` and `playgrounds/` own local microVM lifecycle, pinned Nix development
inputs and host-held recovery archives. They invoke the knowledge bootstrap without
changing tool interfaces, store ownership or review authority. Docker Sandboxes
0.48.0 provides the microVM boundary; the Python launcher runs on the host.

## Domain types

- Distribution manifest: source/version/digest/license, build inputs and capability checks.
- Installation receipt: package revision, installed artifacts and verified capabilities.
- Existing-skill inventory: bounded metadata, full-bundle digest, original location,
  aliases, conflicts and parse limitations. Existing instructions are untrusted data.
- Skill/workflow graph: explicit identities, directed routes, resource hashes and
  labeled inferred relationships. Ranking is not approval or truth.
- Evidence library: immutable source records, exact citations and reviewed analysis.
- Portable records: independent skills, sessions, insights and bookmark snapshots.
- Newsletter edition: frozen public research, cited editorial JSON, revision-bound
  review, HTML/Markdown and an owned checksum manifest.
- Playground identity: owned VM names, the active VM, source hash and Nix lock hash.
- Host share: explicit canonical directory, read-only or writable mode, root identity and per-user lease.
- Checkpoint: stopped guest image, writable host-tree archives, SHA-256 hashes and environment identity.
- Restore journal: staged/replaced host directories, retained original trees and pre-restore VM identity.
- Workspace review: unextracted guest archive, writable host archives, inventories and digests awaiting human review.

## Installation and extension points

`plugins/10x-swe/package.json` packages engineering skills and their resources for
OpenCode v2. `scripts/hosts.py sync` generates its manifest and frontmatter data
from the canonical engineering plugin. `index.js` registers skills, subagents
and namespaced commands through OpenCode transforms. It preserves existing skills
and agents, inherits build-agent permissions and leaves model selection to the
host. Loading writes no harness files and starts no knowledge bootstrap or MCP
connections. npm installation and local archive extraction are explicit operations;
removing the plugin configuration removes its runtime registrations on reload.

The bootstrap plans, installs and verifies tools in an owned prefix. Harness
configuration, source indexing and connector setup are explicit user operations.
Doctor reports installed capabilities and their prerequisites. Connectors, media
extraction, local models and Dagu each have separate setup requirements.

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
Engineering bundles keep canonical workflows and optional references together.
Web research guidance routes to independently available connectors, clients and
provider APIs. The optional search helper inherits credentials and emits JSON;
research acquisition, evidence transformation and reviewed publication stay separate.
The web-research catalog command reads `research-request/v1` from stdin and emits
`research-source/v1` and `research-coverage/v1` JSONL. It owns bounded ZenML,
AIETalks and AI Engineer acquisition with response hashes and timestamped evidence.
The newsletter invokes explicit evidence commands without importing their adapters.
It reserves their source budget, deduplicates original recording URLs and retains
both discovery trails while preferring transcripts over secondary summaries.
Catalog ingestion times and reported years never become publication dates.
The optional newsletter recipe invokes public search/extraction commands, then a
Claude CLI copywriter and independent Codex CLI reviewer over frozen JSON files.
Native event logs retain producer provenance; receipts bind the producer and
input/output hashes. Writer revisions accept explicit feedback JSON; reviewer
inputs remain limited to research and the issue. The local renderer validates
explicit files without opening companion stores. Dagu coordinates those commands under an operator-owned
environment. Newsletter publication never grants insight-library publication.
Feedback may select bounded story copy fields. Claude returns only those strings;
the adapter preserves all other fields and requires review of the complete merge.
Both editorial stages load one shared rubric. Adapter receipts also bind the
adapter source and rubric bytes, so policy changes require fresh editorial work.
An optional synthetic calibration command invokes only the reviewer, keeps expected
labels outside its input and retains verdicts and rationales for operator inspection.
Acquisition searches every configured topic and balances source selection across
topics under explicit source/text limits.
Acquisition substitutes the frozen start date into explicit search arguments;
the independent search helper owns provider-specific publication-date filters.
The local publication reader exposes topic-level search/evidence/story coverage
separately from editorial content.
HTML and Markdown share a current-news/background split and first-use source
numbering by URL. The quick briefing links the first six current stories in
editorial order; earlier or unconfirmed-date reading stays separate. Briefs show
self-contained summaries and essential caveats; deep dives retain full analysis.
Short exact source excerpts are grouped behind an evidence disclosure; full
citation records and timestamp provenance remain in the edition's JSON artifacts.
Its store owns immutable dated editions and marked daily work directories. Seven-day
retention validates ownership, inventory, hashes and symlinks before journaled
removal; interrupted removal resumes without adopting unrelated directories.
Skill authoring owns its initializer, basic metadata validator and construction
checklist. Ghidra's canonical artifacts use address identities, bounded selected
decompilation and identity-checked read-only reuse; native fixtures never run
target bytes. Turnstile's mandatory procedures gate credential operations and
require upstream bundles to pass exact-bundle review before activation.
Source revisions install into fresh prefixes; an owned receipt never silently
upgrades an existing installation. `setup --from OLD` copies only user data
(`knowledge/sources`, `state`) into the new prefix before indexing. The source
and destination must not overlap; migration rejects symlinks and nonempty destination
data directories before copying. Users must stop source writers during migration.
An interrupted copy blocks setup certification; use a fresh destination. After a
completed copy, build retries omit `--from` and retain the copied data.
In Git checkouts, the source fingerprint, staged build inputs and installed
skill/library resources use the same tracked-file inventory. Untracked and ignored files (such as a skill's
node_modules) are neither certified nor installed. Remote publication and delivery
remain separate acts.
Completed setup retries verify readiness without requiring compilers; incomplete
installs still require the documented build prerequisites.
Plan and incomplete setup probe compiler versions, C compilation and Linux OpenSSL
availability before builds. Activation is part of the completed installation:
retries restore a missing deterministic `env.sh`, but refuse modified or symlinked
activation files rather than overwriting them.

The playground copies an explicitly selected project into a private guest workspace.
Explicit read-only shares expose reference repositories, datasets and skills;
writable shares expose selected host projects. `playgrounds/mounts.py` owns share
validation, host archives, user-scoped conflict leases and journaled restoration.
Each shared path is identical on host and guest. A dedicated writable primary leaf
satisfies the runtime contract without exposing sibling host control metadata. Nix
pins Python, Rust, Go, native build tools and workflow dependencies. The existing
bootstrap installs CLIs and mutable stores in the guest's owned knowledge prefix.
Only the repository bootstrap runs during dependency-download access. Workspace
commands run after an explicit per-VM deny-all network rule. Host SSH forwarding
must be disabled, clipboard image access off, and shared agent skills off.

Host metadata/checkpoints never enter the guest. Checkpointing stops writers and
captures the container filesystem, including workspace Git/untracked/ignored files,
local database journals and workflow state. Writable shares have separate native
host tar archives preserving ACLs/xattrs and internal links. Read-only references
remain live. Other host writers must be paused during snapshot, restore and review;
leases exclude overlapping writable playgrounds in the same user state namespace.
Rewind verifies all archives, stages host trees and retains displaced originals,
then starts/checks a new VM before switching identity. Interrupted host replacement
blocks work until explicit `recover` stops guests and rolls back host directories
and VM identity. The stopped previous VM remains recoverable. Review binds both
guest and writable host archives without extracting guest data or granting publication.
See [playground operation](playgrounds/README.md) for lifecycle and recovery.

## Invariants

1. No existing skill, source corpus or conflicting installation is overwritten.
2. A setup failure is not readiness; a skipped capability is not a pass.
3. No implicit cloud AI, bookmark import, session crawl or evidence publication.
4. Artifact hashes bind inspection and installation; paths cannot escape ownership.
5. Discovery, provenance, review and execution authority remain separate.
6. Skills retain distinct triggers, conditions, evidence limits and upstream credit.
7. A failed rewind preserves its checkpoint and previous identity; incomplete host
   replacement blocks admission until explicit recovery restores both sides.
8. Guest execution cannot invoke the host launcher or change host review/network policy.

## Verification

Exercise a fresh isolated installation, repeat setup, interrupted/failed setup,
malformed and duplicate existing skills, changed resource hashes, portable exports,
and the session-to-reviewed-insight path. Test Linux and macOS in CI; only executed
platform checks count as verified. Keep capability-specific prerequisites explicit.
Playground host tests exercise failed/interrupted recovery, unsafe imports,
ownership, locks and pipe contracts. The opt-in microVM acceptance test deletes
guest tools/workspace, restores Git/files/SQLite/workflow state and exercises
independent evidence preparation through review without publication.
Host-share tests cover escaping links, ownership, leases, metadata, checksum failures
before mutation, partial replacement and explicit rollback. A separate microVM
acceptance test deletes data in two host shares and the guest, then rewinds both.
Newsletter tests cover citation/review binding, escaped rendering, immutable
publication, interrupted reader updates, strict retention boundaries, symlink
rejection, cleanup recovery and local environment permissions.

## Further reading

[Documentation](https://github.com/cercova-studios/10x-swe/wiki)
covers setup, composition and platform requirements. Executable contracts and
skill resources stay beside their source for offline use.
