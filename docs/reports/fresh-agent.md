# Fresh-environment onboarding — 2026-10-17

Cloned the published repository at `52b89fe` from GitHub. The initial run used
`env -i`, a new HOME, absent default install prefix, fresh dependency caches and
no installed knowledge commands on PATH. Only host Python, Rust, Go, C compiler
and standard system utilities were exposed. No shell profiles, credentials,
personal knowledge stores or harness settings were inherited.

This was an isolated macOS arm64 shell/home on the existing host, not a new VM or
an independent agent-provider evaluation. Python 3.14, Rust 1.99 and Go 1.27 were
already installed. Bootstrap still requires host build prerequisites and network
access; it does not provision an operating system or toolchains.

## Friction found and fixed

| Observed problem | Change and regression evidence |
|---|---|
| The README's keyword `skill-search path` failed with `topic map unavailable; run skill-search map` | Lexical routing now uses existing typed relationships without a neural map. New Rust and installed-CLI regressions failed before the fix. Semantic routing and stale-map rejection remain enforced. |
| The documented direct workflow failed publication with `ModuleNotFoundError: No module named 'local_embeddings'` | Source-insights resolves its installation-local library from AGENT_KNOWLEDGE_HOME. Acceptance no longer injects PYTHONPATH; it reproduced the failure before the fix. No global Python environment change is needed. |
| Repeated setup failed with `Missing build prerequisite: cargo` after removing compilers from PATH, despite a completed receipt | Completed retries verify readiness before checking build tools. Incomplete setup still rejects missing tools and cannot retain a readiness receipt. |
| Workflow commands assumed `~/.agents`, and the complete recipe was presented through optional Dagu | Documentation now resolves the activated installation and explains the complete shell-only capture, analysis, review, publication and retrieval sequence. Unshipped Dagu server/configuration guarantees were removed. |
| The acceptance test seeded a private session store API | It now starts with an empty index and uses `session-search index --agent codex` against a disposable harness home. |
| A workflow test fixture's interpreter shebang broke in prefixes containing spaces | The fixture uses a quoted shell exec. The Linux/macOS CI prefix now contains spaces and runs that workflow boundary check. |

No new coordinator, store, service, model dependency or coupling between producer
tools was introduced. User approval remains explicit for real publication.

## Checks performed

- Published default-prefix bootstrap and repeat setup passed with fresh caches.
- Fixed source was installed into an absent prefix containing spaces, with no
  carried native build output. Repeat setup with only the Python runtime on PATH
  and subsequent doctor checks passed.
- Five bootstrap tests, four intake tests, twelve graph tests and six concept
  tests passed. Workflow checks covered failed/partial producers, frozen capture,
  stdin, rejected/stale approval, snapshots, recovery receipts and lock rejection.
- Skill-search's complete Rust suite passed: 40 tests, zero failures, one standard
  ignored external graph-fixture test.
- Installed acceptance passed public session indexing, exact turn/line/hash/role
  export, hidden-reasoning exclusion, rejected/stale/approved fixture review,
  deduplicated retry, article provenance, mixed search/graph and reviewed skill links.
- Read-only intake of copies of existing `cli-developer` and `diagnose` bundles
  registered two namespaced unreviewed nodes. Complete source-file hashes remained
  unchanged; their helper scripts were never executed.
- A retained shell workflow published one explicitly synthetic test insight into
  a disposable library. The separate insights viewer retrieved it. Mixed session,
  insight and skill packets remained searchable/navigable while the source-insights
  producer library was temporarily moved away.
- The real missing-import failure occurred after the immutable entry was saved.
  After repair, retry recovered publication/export receipts and retained exactly
  one entry. The saved note, INDEX.md link and retained citation were inspected.
- Distribution checks and diff whitespace passed. No personal library was published
  into, source session crawled, cloud model invoked or Kindle/device setup included.

The source build emitted a nonfatal host Rust stripping warning about a missing
`libLLVM.dylib`; compilation and tests exited successfully. No host toolchain was
modified to hide that warning.

## Construction review

Result: `construction-reviewed` for the changed local behavior and documentation;
no remote scanner acceptance is claimed. Changed Rust routing, Python resource
resolution, the workflow fixture, associated docs, bootstrap order and acceptance
checks were inspected. Unchanged bundle resources retain the published baseline's
provenance and licenses. No new external write, credential, execution or upload
authority was added. Graph creation/freshness was exercised through source setup,
intake and export. The codebase-memory index does not cover this clone; source and
runtime checks were used rather than claiming complete graph-derived impact.

Bundle digests are recorded below as SHA256 of canonical sorted compact JSON
mapping relative filenames to content SHA256, excluding build/bytecode caches:

| Bundle | Reviewed content digest |
|---|---|
| skill-graph | `8709e002256f4e0e6328c762fca327cba756056d76a9c8a2f6426673ebfb619d` |
| source-insights | `af0cee66707d7d21fcc6a2473611858a2839ca094951d09629ac8139cdec14f6` |

The Linux/macOS workflow includes the expanded acceptance path. A hosted rerun
will validate the published fixes; the earlier successful run covers the previous
revision only. Local evidence above does not substitute for that hosted result.

## Limits

The session and publication approvals were explicitly synthetic test fixtures,
not fabricated human approval of real learning. This does not establish recall
quality over personal sessions or agent task performance. Live connectors, Neon,
neural models, Dagu UI/human-task execution and browser/terminal drag hardware
were not exercised. Tools remain independent and personal Kindle delivery stays
excluded. Retained local installation, records, notes and logs are task-owned
reproduction artifacts, not part of the source distribution.
