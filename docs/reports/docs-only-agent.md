# Docs-only fresh-agent trial — 2026-10-17

A native subagent with no inherited conversation followed the published repository
at `77c6c79`, using only Markdown docs and CLI help. It had a separate clone,
fresh HOME, absent installation prefix, explicit host compiler paths, copies of two
existing skill bundles, and one frozen real Codex session. It did not reuse global
skills, memories, existing tools, private imports or fixture seeding APIs.

The local session snapshot, command audit, selected evidence and authored insight
remain private task artifacts. They are not included in this repository.

## Baseline outcome

- Source bootstrap and explicit doctor passed. Sandbox DNS failures required the
  same clone/setup commands to retry with network access; these were harness
  constraints, not product failures.
- Both existing skill bundles were inspected and explicitly indexed as namespaced,
  unreviewed data. All eight input files remained unchanged; helpers were not run.
- The selected harness index contained exactly the one supplied real session.
  Three bounded public tool excerpts retained native session/turn identities,
  JSONL lines/pointers, timestamps, original record hashes and excerpt hashes.
- The agent authored one cited inference with explicit partial coverage and
  chronology limits. Captured written reports were distinguished from observed
  tool output. Historical checks were not rerun or presented as current results.
- Capture, preparation and baseline review succeeded without source inspection.
  The proposed destination and publication receipt did not exist; the installed
  source library exported zero insight nodes. No approval decision was submitted.
- Independent checks matched the frozen snapshot to the original session prefix,
  verified selected original-record/excerpt hashes, and checked the authored quotes
  and prepared hashes. Adapter decoding and excerpt offsets were not independently
  reimplemented by the fresh agent.

The fresh agent's auxiliary inspection scripts had a no-hit-file assumption and a
structured-output decoding assumption. These were recorded as trial-helper errors,
not product defects; neither triggered a producer workaround or publication.

## Review gate friction and fix

Independent adversarial checking found that baseline `review` emitted a digest for
an analysis quoting text absent from retained evidence. Preparation validated the
session packet, but baseline review did not validate authored analysis citations;
the publisher would reject them only later. A review-only workflow needs that
failure before asking a user to review a packet.

`source-insights validate WORK ANALYSIS` now exposes the existing source-specific
validator as a read-only CLI. It checks analysis structure, coverage, citations
and prepared hashes without an installation/search runtime, library creation,
indexing or publication. The external session recipe calls this public command
before returning a digest, rechecks its artifact binding, and includes the
validation result. It imports no other tool or private store. Invalid input emits
no review packet. A digest still grants no publication authority or claim truth.

Docs now identify the review-only stop point and retained packet explicitly.
Changed recipe resources require a new review digest, as before.

## Verification

The invalid-quote regression failed before the fix. Afterward, all eight bootstrap
and review unit tests passed, including changed-evidence rejection, clean malformed
input errors, standalone validation without companion tools, and unchanged work
files/no library effects on successful validation. Twelve graph tests, the
independent session-preparation checks, distribution checks and diff whitespace
also passed. These checks never invoked publication.

The real draft passed the new validator without publication. A fresh-agent retry
against the updated published docs is recorded after its handoff is verified.

Local changes are construction-reviewed for the modified CLI/recipe/docs and
their denial tests. Unchanged resources retain baseline provenance/licenses; no
scanner acceptance, extra credentials, service or execution authority is implied.

## Limits

This is one macOS keyword-profile agent trial, not a cross-harness performance
benchmark or full-session review. Optional models, live connectors, Dagu UI,
historical project checks and device delivery were not exercised. No personal
insight was published. Tools remain independent; Kindle delivery stays excluded.
