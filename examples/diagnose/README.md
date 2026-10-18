# Your first diagnosis

Use the diagnose skill on a small Python CLI before trying it on a project. This
exercise contains an intentional bug and uses only Python's standard library.
It simulates failed attempts; it makes no network requests.

## 1. Make a disposable copy

From the repository root, in a macOS or Linux shell:

```sh
DEMO=$(mktemp -d)
cp examples/diagnose/retry_cli.py "$DEMO/retry_cli.py"
cd "$DEMO"
python3 retry_cli.py --retries 0
```

The output is `{"max_retries": 3, "attempts": 4}`. The intended contract is:

- Omitting `--retries` permits three retries, for four total attempts.
- Explicit `--retries 0` permits no retries, for one total attempt.
- Negative and non-integer values are invalid.

## 2. Load the guide

With the plugin installed at user scope, start Claude Code in the disposable
directory and invoke the command below. If you chose `--scope local`, install
`10x-swe@10x-swe --scope local` from your terminal in this disposable directory
first, using `claude plugin install`.

```text
/10x-swe:diagnose retry_cli.py mishandles --retries 0. It should allow zero retries and one total attempt; omitted retries should still default to three. Reproduce the bug, add a failing regression, make the smallest fix and verify the boundary cases.
```

For another harness, have the agent read the repository's
[diagnose guide](../../plugins/10x-swe/skills/diagnose/SKILL.md) by its absolute path.
If the knowledge CLI tools are installed, activate the printed `env.sh` in that
shell and discover/load the same guide:

```sh
skill-search search 'debug a regression' --limit 5
skill-search load plugin/10x-swe/diagnose
```

Give the returned instructions and the task above to your agent. These commands
print discovery results and guide text; they do not invoke the agent or fix code.

## 3. Check the result

The agent should retain evidence of a regression failing before the fix, then
show it passing. Verify the original input yourself:

```sh
python3 retry_cli.py --retries 0
python3 retry_cli.py
python3 retry_cli.py --retries 2
python3 retry_cli.py --retries -1  # Expected argument error
python3 retry_cli.py --retries one  # Expected argument error
```

The first three outputs should contain `(max_retries, attempts)` pairs of `(0, 1)`,
`(3, 4)` and `(2, 3)`. Both invalid inputs should exit with status 2. Ask for the
cause and the tests run, not just a claim that the code is fixed. Keep changes in
the disposable directory; the intentionally buggy source fixture stays unchanged.
