<div align="center">

# 10x-swe

**Engineering workflows and searchable knowledge for your coding agent.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

*Discover → Investigate → Verify → Reuse*

</div>

10x-swe is a plugin marketplace for terminal agents. Its skills are task-specific
guides your agent reads: how to investigate a bug, refactor safely, or review a
change. Its knowledge tools help you find and reuse material from skills, past
sessions, bookmarks and articles.

Use it to:

- **Investigate and fix code:** follow workflows for reproduction, diagnosis, small changes and verification.
- **Find prior work:** search skills and sessions, then explore related skills and workflows in a terminal graph.
- **Keep useful lessons:** extract reading material, prepare cited insights, review them and save them for later retrieval.

## Quick start

| Route | Choose it for | Setup |
|---|---|---|
| [Engineering skills only](#engineering-skills-only) | Debugging, review, testing and refactoring. **Start here.** | Install the `10x-swe` plugin |
| [Knowledge CLI tools](#knowledge-cli-tools) | Search skills and sessions, convert articles and keep reviewed insights | Build tools separately; optionally install the `knowledge` instruction plugin |
| [Optional playground](#optional-recoverable-playground) | Run work in a recoverable local microVM | Docker Sandboxes and the host setup guide |

### Engineering skills only

With Claude Code installed, run these commands in your terminal:

```sh
claude --version
claude plugin marketplace add cercova-studios/10x-swe
claude plugin install 10x-swe@10x-swe
claude plugin list
```

The install defaults to user scope, so it applies across your projects on this
computer. For only the current repository, add `--scope local` to the install
command. This two-step marketplace/install sequence is the canonical route here.
The shorter `--marketplace` install option requires Claude Code v2.1.292 or later;
see the [official command reference](https://code.claude.com/docs/en/plugins/cli-reference#plugin-install)
and `claude plugin install --help` for your version.

Check that `claude plugin list` shows `10x-swe@10x-swe` enabled. Start a new session
in your project and type `/10x-swe:diagnose`; it should appear in the command picker.
Then give it a concrete task, for example:

```text
/10x-swe:diagnose npm test fails on parser.spec.ts after the last merge. Reproduce the failure, identify the cause, and verify the smallest fix.
```

Expect the agent to reproduce the failure, add a regression, make a scoped fix and
report verification. For a disposable Python-only exercise, try the
[first diagnosis walkthrough](examples/diagnose/README.md). If the skill is missing,
check the Installed and Errors tabs in `/plugin` before troubleshooting your task.

The skill guides the investigation; the agent still needs to execute and check
its work. Engineering-only setup is complete here. Optional tools used by individual
skills have their own prerequisites; Rust, Go and Docker are for the routes below.
See the linked [skill, agent and command catalog](plugins/10x-swe/README.md).

For other harnesses, use their documented skill-loading mechanism or explicitly
ask the agent to read a selected `SKILL.md` from this checkout. Preserve its sibling
resources. This is manual integration, not automatic plugin registration.

## Setup

### Knowledge CLI tools

The [knowledge plugin](plugins/knowledge/README.md) provides instructions. Installing
it does not build the executables. To add its instructions in Claude Code after
registering the marketplace above:

```sh
claude plugin install knowledge@10x-swe
```

To build the tools, use macOS or Linux/WSL with Python 3.11+, Rust 1.88+,
Go 1.22+, a C compiler and network access. Linux also needs OpenSSL
headers and pkg-config. The [CI toolchain pins](.github/workflows/portable.yml)
are a reproducible starting point. Rust 1.88 is the declared minimum in current
locked dependencies; use the CI-pinned toolchain for the tested version. Future
dependency updates may raise that minimum. See [platform requirements](https://github.com/cercova-studios/10x-swe/wiki/Platforms).

```sh
git clone https://github.com/cercova-studios/10x-swe.git
cd 10x-swe
./knowledge plan
./knowledge setup
# Run the env.sh activation command printed by setup in this shell.
./knowledge doctor
command -v skill-search
```

`plan` reports compiler identity/version, C compilation and Linux OpenSSL checks
alongside the planned effects. It does not download dependencies or prove the full
build will succeed. Resolve any failed `build_checks` before setup. `doctor`
verifies a completed installation. Setup builds tools and indexes bundled skills.
Skill discovery and source-insights use local keyword indexes. For bookmark search
without a model, pass `--lexical-only` to `bkd search`; its native default can require
the optional BGE model. Success means doctor reports
`"status": "passed"` and `command -v skill-search` points into your chosen prefix.

For isolation, append `--prefix "/absolute/new/path"` to plan, setup and doctor.
Use the same path for all three. Activate its `env.sh` in each new shell; setup
does not edit shell profiles or configure your agent harness.

| Symptom | Next step |
|---|---|
| Missing build prerequisite or dependency build failure | Install the stated prerequisite, then rerun setup against the same prefix and unchanged checkout |
| No completed installation receipt | Fix the original setup error and rerun setup; doctor does not install tools |
| `skill-search` is not found | Source the printed `env.sh` in the current shell, then check `command -v skill-search` |
| `env.sh` is missing | Rerun setup with the same source and prefix; it restores activation and prints the next step |
| Prefix belongs to different source bytes | Keep the old prefix and build this revision into a fresh prefix |
| Local graph is stale after an intentional skill change | Run `skill-search refresh --lexical` and retry discovery |

Default data stores live inside the prefix. A fresh-prefix upgrade starts with new
stores; preserve your old prefix and any explicitly configured library/index paths.
Reactivate the old `env.sh` to switch back. See [setup and recovery](https://github.com/cercova-studios/10x-swe/wiki/Getting-started)
before moving existing data.

### Optional recoverable playground

Choose this route when you want a private Linux microVM with Nix-pinned tools and
host-held checkpoints. It requires Python 3.11+ and Docker Sandboxes 0.48.0.
Complete the [one-time host setup](playgrounds/README.md#one-time-host-setup), then
run these commands from the checkout:

```sh
./playground doctor
./playground up demo
./playground run demo -- python3 --version
./playground checkpoint demo baseline
./playground rewind demo baseline
./playground review demo
```

Add `--workspace PATH` to start with a project copy, `--read-only PATH` for
references, or `--writable PATH` for a host project covered by checkpoint and rewind.
Commands run offline; review returns archives for inspection before publication.
See the [playground guide](playgrounds/README.md) for shells, pipes, recovery and teardown.

## Usage

### Find skills and bring your own

After setup and activation, discover an entrypoint, inspect its text, then give it
a task. A bundled diagnosis route is:

```sh
skill-search search 'debug a regression' --limit 5
skill-search load plugin/10x-swe/diagnose
```

Search returns IDs and descriptions; `load` prints the selected instructions.
For other tasks, use the exact ID returned by search. Ask your agent to follow the
loaded guide on a specific failure, or use the [disposable diagnosis exercise](examples/diagnose/README.md).
Loading is inspection: it does not run code, grant permissions or prove a fix.

Explore related routes or register your own skills next:

```sh
skill-search path 'capture reusable session learning'
skill-search related plugin/10x-swe/diagnose
skill-search export > skills.jsonl   # Noninteractive skills and relationships
skill-search graph                  # Interactive terminal; q exits

knowledge-intake --root codex=/absolute/path/to/skills --output intake.json
# Review the report before registering existing skills for discovery.
knowledge-intake --root codex=/absolute/path/to/skills --index
```

Intake reports duplicates and conflicts while preserving source bundles.
Indexed skills remain unreviewed; inspect them before loading their instructions.

### Connect the tools with pipes

Each tool works independently. Combine exported records without coupling their
storage implementations:

```sh
skill-search export --query 'topic' --limit 5 > skills.jsonl
source-insights export > insights.jsonl
cat skills.jsonl insights.jsonl | bkd --records - search 'topic' --lexical-only --list
```

Check each export succeeds before consuming its file; use `pipefail` when streaming.
For [session to insight](plugins/knowledge/skills/source-insights/workflows/session-to-insight.md),
select a session, prepare evidence, write an analysis, review it and publish with
approval. Dagu can optionally coordinate the same shell workflow.

## Documentation

[Guides and examples](https://github.com/cercova-studios/10x-swe/wiki) · [Tool capabilities](plugins/knowledge/README.md) · [Skill catalog](plugins/10x-swe/README.md) · [Architecture](ARCHITECTURE.md) · [Help and issues](https://github.com/cercova-studios/10x-swe/issues)

## License

[MIT](LICENSE). Bundled tools and skills retain their upstream licenses and credits.
Maintained by [Rohit Nair](https://github.com/rnair98).
