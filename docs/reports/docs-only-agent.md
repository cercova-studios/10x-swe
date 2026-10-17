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

The same fresh agent pulled published `0fa385d` and followed the updated documented
standalone route, without source inspection or reinstalling the unchanged native
tools. Capture, preparation, standalone validation and review passed against the
same real-session packet and byte-identical analysis. An isolated absent quote
was rejected by both validation and review with no digest or library effects.

The integrator verified all eight input skill hashes, unchanged baseline artifacts,
the original session-prefix hash, and the new review digest from its exact files
and recipe resources. The 25 baseline and 13 retry product commands contained no
publish invocation, decision submission or human-task completion. Both proposed
destinations remained absent; the installed source library had zero insight entries.
The private final review, analysis and evidence are retained for the user. This
trial ends at review and does not grant permission to publish them.

Local changes are construction-reviewed for the modified CLI/recipe/docs and
their denial tests. Unchanged resources retain baseline provenance/licenses; no
scanner acceptance, extra credentials, service or execution authority is implied.
The reviewed source-insights bundle content digest is
`174606c48bd6fcbc27eb28369b94729cf46d1b5325b727c01bebd269486e3d75`
(SHA256 of sorted compact JSON mapping relative files to content SHA256, excluding
bytecode caches). The changed recipe calls the source owner through its public
read-only CLI; no companion producer, model or private index is required.

## Hosted integration

The [Linux/macOS run](https://github.com/cercova-studios/terminal-agent-plugins/actions/runs/39070041946)
completed successfully at `0fa385d875bb3bd1280399b6354762867e2510f0`.
Both job conclusions and logs were inspected on 2026-10-17. Each platform passed
fresh source setup, repeat setup, eight bootstrap/review tests, the installed
workflow checks, 147 Rust tests, Go tests and vet. The three standard ignored
tests still require an external mapped graph fixture, local neural model or
disposable PostgreSQL; they were not exercised by this run.

Hosted workflow publication checks use synthetic fixtures in disposable stores.
The real-session draft and its review artifacts were never supplied to CI or
published. The subsequent report update changes documentation only.

## Limits

This is one macOS keyword-profile agent trial, not a cross-harness performance
benchmark or full-session review. Optional models, live connectors, Dagu UI,
historical project checks and device delivery were not exercised. No personal
insight was published. Tools remain independent; Kindle delivery stays excluded.
