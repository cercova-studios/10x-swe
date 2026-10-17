# Hosted validation — checked 2026-10-17

Published to `cercova-studios/terminal-agent-plugins` on `main`:

- `f4558ae`: portable bootstrap, independent tool sources and 10x-swe cleanup.
- `4133e7f`: supply the pinned Pandoc prerequisite for real EPUB regression tests.

The [first Linux/macOS run](https://github.com/cercova-studios/terminal-agent-plugins/actions/runs/38844234146)
passed fresh setup, repeated setup, standalone pipes, reviewed publication and
read-only existing-skill intake on both platforms. Both regression jobs then failed
at `cover::tests::mandatory_cover_journey_cache_failure_concurrency_and_exact_lettering`:
`EPUB export requires Pandoc on PATH`.

CI now downloads official Pandoc 3.12.1 archives for its Linux x86_64 and macOS
arm64 runners and checks their upstream SHA256 digests before extraction. This step
runs after core setup/intake, preserving proof that the default bootstrap needs no
Pandoc. The previously failing test passed locally using the exact downloaded
binary. No assertions or tests were removed, weakened or bypassed.

The [complete rerun on 4133e7f](https://github.com/cercova-studios/terminal-agent-plugins/actions/runs/38845172779)
finished successfully on 2026-10-16 UTC. Both job conclusions and logs were checked
on 2026-10-17. The tested revision is
`4133e7faeabe88b476cbfa572a4bac6e266f8491`.

| Check | Linux x86_64 | macOS arm64 |
|---|---|---|
| Fresh source build and repeated setup | Passed | Passed |
| Independent pipes, review gates and read-only intake | Passed | Passed |
| Source-only distribution and concurrent graph publication checks | Passed | Passed |
| Pinned Pandoc archive verification and installation | Passed | Passed |
| Rust regressions, including the previously failing EPUB test | 146 passed, 3 ignored | 146 passed, 3 ignored |
| Go tests and vet | Passed | Passed |

The three standard ignored Rust tests require an explicit mapped graph fixture,
a pinned local neural model, or disposable PostgreSQL. They were not exercised by
hosted CI. The separate local graph-fixture check is recorded in
[local acceptance](acceptance.md).

The final validation update changes documentation only; executable sources, locks,
tests and the workflow remain identical to the tested revision. No additional
full build is required for that documentation follow-up.

Tools continue to own separate stores and exchange explicit records/files. Personal
Kindle delivery, device configuration and SSH aliases remain excluded. Live
connector/Neon publication and optional neural-model tests are outside this CI
profile; existing optional test skips remain explicit.
