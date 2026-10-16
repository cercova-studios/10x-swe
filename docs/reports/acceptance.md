# Portable knowledge acceptance — 2026-10-14

Implemented in an isolated clone; the pre-existing dirty checkout, installed global
skills/tools, personal libraries and website were not modified. Nothing was committed,
pushed or deployed.

## Delivered behavior

- `knowledge plan/setup/doctor`: source-built, hash-locked Python dependencies,
  Cargo locks, native Go viewer, owned prefix and final installation receipt.
- Explicit keyword profile: no model, SQLite vector extension, service, cloud AI,
  session crawl, connector/import or publication required during setup.
- Six independent tools plus read-only intake. Typed JSONL/files preserve citations,
  revisions, coverage, review state and separate corpus ranks. A stateless local model
  primitive is shared; no tool imports another producer's storage implementation.
- Existing-skill inspection/registration preserves source bytes and labels indexed
  nodes unreviewed. Duplicate bundles, aliases, same-name conflicts, malformed input,
  bounds and unresolved references remain visible. Helpers never run during intake.
- Seven common 10x-swe entrypoints: 8,135 → 1,726 words (78.8% smaller), preserving
  distinct roles, verification and authority limits. Specialist skills remain: 69
  engineering skills total. Skill-authoring references/workflows now use explicit
  output paths; the ambient directory helper and default MCP configuration are retired.
- Kindle delivery, device/SSH configuration and personal wrappers are excluded.
  Generic EPUB conversion and the optional independent KFX converter adapter remain.

## Checks actually run

Host: macOS arm64, Python 3.14.5, Rust 1.99.0, Go 1.27.2.

| Check | Observed result |
|---|---|
| Fresh `knowledge setup` from an absent `/tmp` prefix, no carried native target directory | Passed; canonical path resolves correctly, 310 artifact hashes, 76 skill/workflow nodes and 16 declared edges |
| Repeat setup and doctor against that prefix | Passed; no rebuild or source-store mutation |
| Installed session → exact-turn export → evidence preparation → review → insights → explicit mixed search/graph | Passed with synthetic public fixtures and isolated stores |
| Rejected approval, edited evidence, changed destination and approved retry | Denied stale/rejected publication; approved publication deduplicated |
| Distiller stdin → prepared article with original HTML snapshot | Passed; exact source/snapshot hashes and citations retained |
| Existing-skill CLI intake and graph export | Passed; aliases/exact duplicates detected, same-name variants retained, malformed metadata reported, sources unchanged, unreviewed state survives export |
| Bootstrap ownership/failure checks | 4 passed; unowned/conflicting prefix, source mismatch, missing readiness and artifact tampering rejected |
| Intake unit checks | 4 passed; duplicate/conflict/resource identity, hidden omissions, YAML aliases and directory cycles |
| Graph inventory and concept lifecycle | 12 + 6 passed |
| Concurrent root publication | Passed; stale proposal cannot overwrite new roots and lock releases on rejection |
| Session recall/provenance regressions | Passed, including late turns, role filtering, redaction, no hidden reasoning, malformed records and failed refresh preservation |
| Prepared evidence, session preparation and review/failure-recovery journeys | Passed; no producer executable required by the consumer |
| Native Rust suites | 146 passed; 3 optional tests ignored by the standard invocation |
| Additional graph layout test on separately mapped real package inventory | Passed unchanged: 76 nodes, 10 overview glyphs; uses cached pinned BGE locally, no downloads/cloud |
| Standalone Go tests and vet | Passed |
| Distribution sensor and diff whitespace | Passed; valid skill metadata, no detected personal absolute paths/credential patterns/native binaries/model weights, retired ambient contracts absent |
| Dagu 2.19.2 workflow dry-run | Parsed and simulated; review-output placeholders warn because dry-run supplies no human response |

The graph layout test was first run against the keyword-only graph and failed its
neural-cluster aggregation assertion (76 individual glyphs). The test was not changed
or weakened. It passed against a separately generated neural map. The keyword profile
kept its original graph; unit checks cover its unmapped rendering/navigation behavior.

Early clean builds exposed and fixed a Rust variable collision, unnecessary vector
extension loading in keyword mode, an invalid doctor subcommand, and an article
example using the legacy JSON shape. Failed setups did not retain readiness receipts.
Final fresh setup and pipes were rerun after the fixes and skill-authoring cleanup.

## Reproduce the core acceptance

From the repository root, choose an absent prefix outside the source checkout:

```sh
./knowledge plan --prefix /absolute/new/prefix
./knowledge setup --prefix /absolute/new/prefix
./knowledge setup --prefix /absolute/new/prefix
python3 tests/acceptance.py /absolute/new/prefix
./knowledge doctor --prefix /absolute/new/prefix
```

Use the installed runtime for metadata/unit sensors:

```sh
RUNTIME=/absolute/new/prefix/runtimes/source-insights/bin/python
export PYTHONPATH="$PWD/plugins/knowledge/lib"
export PYTHONDONTWRITEBYTECODE=1
"$RUNTIME" -m unittest discover -s tests -p 'test_*.py'
"$RUNTIME" -m unittest discover -s plugins/knowledge/tests
"$RUNTIME" tests/check_concurrent_graph.py
"$RUNTIME" tests/check_distribution.py
```

The acceptance script registers temporary external fixtures and removes that
registration before deleting their source directory. Run it against a test prefix,
not an installation being edited concurrently.

## Limits retained explicitly

- Linux/WSL execution is unverified locally: the existing Podman socket refused
  connection. Linux/macOS CI is defined but has not run on GitHub. Native Windows
  is unsupported. The actions use their documented [checkout](https://github.com/actions/checkout/tree/v4),
  [Python](https://github.com/actions/setup-python/tree/v5) and [Go](https://github.com/actions/setup-go/tree/v5) inputs.
- The optional bkd neural-retrieval and disposable-PostgreSQL tests were not run.
  Real connector credentials, Neon publication, terminal/browser drop hardware,
  optional PDF/media providers and a live Dagu human-task roundtrip were not exercised.
  Script-level review gates and recovery were exercised; dry-run is not live execution.
- Keyword search does not provide neural paraphrase ranking. Neural graph mapping
  was tested with an existing local model, not a model-installation workflow.
- Fresh prefixes are the upgrade/rollback boundary. Setup does not migrate existing
  personal stores, activate harness configurations, or automatically trust external skills.
- A force-killed graph writer can leave its existing directory lock. Writers fail
  visibly rather than guessing that another operation is dead; inspect the owned
  interrupted operation before removing its lock. Ordinary exceptions release locks.
- Pattern sensors are bounded checks, not secret-scanner clearance or full security
  audits. No scanner acceptance is claimed. The clone has no codebase-memory index;
  structural conclusions used direct source inspection and runnable checks instead.
