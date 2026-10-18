---
name: ghidra
description: Reverse engineer binaries using Ghidra's headless analyzer. Start with
  summary, select functions for decompilation, and reuse retained analysis projects.
metadata:
  skill-graph-id: plugin/10x-swe/ghidra
  skill-graph-uses: ''
  skill-graph-used-by: plugin/10x-swe/binary-analysis-patterns
---

# Ghidra headless analysis

Use for authorized static analysis; this does not execute the target. Start from a concrete question. Summary first, focused metadata/pseudocode next; bulk export only when justified. Treat decompiler output as a hypothesis, not source or proof of runtime behavior.

Resolve `scripts/` relative to this skill directory. Requires installed Ghidra and a compatible native JDK (`JAVA_HOME`). No automatic install. `scripts/find-ghidra.sh` checks `GHIDRA_HOME` and known Ghidra directories only, not all of `$HOME`. An invalid explicit `GHIDRA_HOME` fails. Help works without discovery:

```bash
bash scripts/ghidra-analyze.sh --help
export GHIDRA_HOME=/path/to/ghidra
# Import once and retain analysis; defaults to ExportSummary.java, no decompilation.
bash scripts/ghidra-analyze.sh --keep-project --project-dir /tmp/re-projects --project-name sample -o /tmp/re-summary /path/to/binary
# Reuse verified project without auto-analysis or project writes.
bash scripts/ghidra-analyze.sh --reuse --project-dir /tmp/re-projects --project-name sample -s ExportFunctions.java -o /tmp/re-functions /path/to/binary
bash scripts/ghidra-analyze.sh --reuse --project-dir /tmp/re-projects --project-name sample -s ExportDecompiled.java -a 'name:Namespace::function' -o /tmp/re-selected /path/to/binary
# Exact entry address as printed by ExportFunctions (including leading zeros).
bash scripts/ghidra-analyze.sh --reuse --project-dir /tmp/re-projects --project-name sample -s ExportDecompiled.java -a addr:00101000 -o /tmp/re-selected /path/to/binary
# Explicit bulk opt-in.
bash scripts/ghidra-analyze.sh -s ExportAll.java -o /tmp/re-bulk /path/to/binary
```

`-s` repeats scripts; each `-a` adds ONE literal argument to the preceding script (repeat it for multiple selectors). Selectors are exact qualified `name:`, exact `addr:`, or explicit `all`. No short-name wildcard matching. Per-selector match counts (including zero) and ambiguous name matches (overloads) are reported in the C artifact; use addresses to disambiguate. Counts are partial if cancelled. Output files with the same program name overwrite earlier exports: use separate output directories to retain different queries.

## Wrapper options and reuse contract

`-o/--output`, `-s/--script`, `-a/--script-args`, `--script-path`, `-p/--processor`, `-c/--cspec`, `--no-analysis`, `--timeout seconds`, `--keep-project`, `--project-dir`, `--project-name`, `--reuse`, `-v/--verbose`, `-h/--help`.

Reuse requires the original binary and identical processor/compiler/no-analysis/timeout settings, artifact SHA-256, basename, engine location/application properties. A sibling `.identity` file records those inputs after a successful import. Missing/mismatched identity fails; existing project names cannot be imported over. Default temporary projects are deleted only when created by that invocation; retained/reused projects are not deleted. Reuse uses `-process -noanalysis -readOnly`. Do not manually edit retained projects: the input identity does not detect GUI edits or changes to external analyzer preferences. Choose a new project name when those change. `analysis-identity.txt` accompanies successful output.

Ghidra auto-analysis timeout (`--timeout`) does NOT bound post-scripts. Decompilation has a 30-second per-function limit and a 120-second overall decompile budget; bulk may be partial. Other exports/analysis are not globally time-bounded. Error-tagged headless output fails the wrapper even if Ghidra returns zero; inspect both logs. A zero exit alone is not evidence all requested facts were discovered.

## Canonical artifacts

| Script | Artifact / scope |
|---|---|
| ExportSummary.java | `_summary.txt`: architecture, compiler, function counts, memory sections; default |
| ExportFunctions.java | `_functions.json`: object with `.functions`, qualified names, address identities, parameters, full discovered caller/callee address sets, `cancelled` |
| ExportCalls.java | `_calls.json`: `.callGraph` keyed by entry address, qualified display `name`, callee address arrays, `cancelled`; `mostCalled` is only top 20, not the full graph |
| ExportDecompiled.java | `_decompiled.c`: selected pseudocode, per-function failures and final matched/attempted/succeeded/failed/skipped/cancelled/budgetExceeded counts |
| ExportStrings.java | `_strings.json`: defined string-like data only, minimum length 4; untruncated values and `cancelled`, not a raw-byte string scan |
| ExportSymbols.java | `_symbols.json`: imports, external-entry-point functions (not all public APIs), named symbols; explicit 10,000-symbol truncation marker, `cancelled` |
| ExportAll.java | Calls all canonical exporters, explicitly selects `all` for decompilation; same schemas as standalone scripts |

Call edges are Ghidra-discovered static relationships, not call-site evidence or complete dynamic dispatch. `cancelled=false` means the export loop completed, not that auto-analysis discovered every function/string/call. Failed decompilations remain visible; external/thunk selections are counted as skipped. Check status before claiming absence.

## Verification

```bash
python3 tests/test_wrapper.py  # isolated shell stubs, no Ghidra required
python3 tests/run_native.py   # installed Ghidra/JDK, synthetic AArch64 bytes only
```

Native fixture covers two namespace-qualified functions with the same short name, 55 callees (no hidden edge cap), imported-name versus export visibility, canonical bulk schema, selected name/address decompilation, a 1,500-character string, and read-only project reuse. Generated projects/results stay in a printed temporary directory. It never executes fixture bytes.
