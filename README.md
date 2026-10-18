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
| [Other agents](#other-agents) | The same skills in Codex, Grok Build, Copilot CLI, opencode (free models) or pi | One install command per host |
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

Running Claude Code sessions needs a paid Claude plan or an Anthropic API key. To use
another agent, or to try the skills for free with opencode, see [other agents](#other-agents).

### Other agents

The skills are plain [Agent Skills](https://agentskills.io/specification) folders, so
other agents load the same files. Install for your agent, then run its verify step
before giving it a task like the diagnose example above.

| Agent | Cost to run a session | Loads |
|---|---|---|
| OpenAI Codex CLI | ChatGPT plan sign-in or OpenAI API key | skills |
| Grok Build | xAI sign-in or `XAI_API_KEY` | skills, agents, commands |
| GitHub Copilot CLI | GitHub Copilot plan | skills (agents and commands unverified) |
| opencode | **Free models available, no key** | skills, commands, agents (translated) |
| pi | Your own provider key, or a local model | skills, commands as prompt templates |
| Any other Agent Skills host | Varies | skills |

#### OpenAI Codex CLI

```sh
codex plugin marketplace add cercova-studios/10x-swe
codex plugin add 10x-swe@10x-swe
codex plugin add knowledge@10x-swe        # optional
```

Verify: `codex plugin list` shows the plugins as installed, and `/skills` in a session
lists `10x-swe:diagnose` and friends. Codex plugins carry skills and MCP servers only,
so the agents and slash commands are not available; the main commands have skill
equivalents (for example `/research` → the `code-research` skill). Codex reads the
generated [`.agents/plugins/marketplace.json`](.agents/plugins/marketplace.json).
Running a session needs a ChatGPT sign-in or `OPENAI_API_KEY`.
[Plugins](https://developers.openai.com/codex/plugins) ·
[Skills](https://developers.openai.com/codex/skills)

#### Grok Build

```sh
grok plugin marketplace add cercova-studios/10x-swe
grok plugin install 10x-swe --trust
grok plugin enable 10x-swe
```

Verify: `grok inspect --json` lists the 10x-swe skills, agents and commands. Plugins
are off until installed with `--trust` and enabled. Grok Build reads the Claude Code
marketplace directly. Running a session needs an xAI sign-in or `XAI_API_KEY`.
[Plugins](https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-pager/docs/user-guide/09-plugins.md)

#### GitHub Copilot CLI

```sh
copilot plugin marketplace add cercova-studios/10x-swe
copilot plugin install 10x-swe@10x-swe
```

Verify: `copilot plugin list` shows the plugin and `copilot skill list` (or `/skills list`)
shows its skills. Copilot reads the same marketplace through
`.github/plugin/marketplace.json`. Agents and commands use Claude Code's file layout and
have not been verified in Copilot. Running a session needs a GitHub Copilot plan.
[Plugin reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-plugin-reference)

#### opencode (free)

opencode has no skill marketplace, so link the bundles into a project (or into
`~/.config/opencode` for every project). Needs Python 3 and PyYAML (`pip install pyyaml`).

```sh
git clone https://github.com/cercova-studios/10x-swe.git ~/src/10x-swe
cd your-project
python3 ~/src/10x-swe/scripts/hosts.py link opencode --dest .opencode
opencode models opencode               # pick a model marked free
opencode run -m opencode/MODEL "Use the diagnose skill: ..."
```

Verify: `opencode debug skill` lists the 72 skills and `opencode debug agent
code-reviewer` prints the translated agent. The link step symlinks skills and
commands and writes opencode-format copies of the agents (opencode rejects Claude
colour names and model aliases). Rerun it after `git pull`; `--unlink` removes only
what it created. [Skills](https://opencode.ai/docs/skills/) ·
[Agents](https://opencode.ai/docs/agents/) · [Commands](https://opencode.ai/docs/commands/)

#### pi

```sh
pi install git:github.com/cercova-studios/10x-swe       # add -l for this project only
```

Verify: start `pi` and type `/skill:` to see the skills, or `/` for the prompt
templates (`/research`, `/create-prompt`, ...). The root `package.json` is a
[pi package](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/packages.md)
listing both plugins' skills and the 10x-swe commands. pi has no subagents, so the
agents are not loaded. Bring your own provider key or a local model.
[Skills](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/skills.md)

#### Any other Agent Skills host

Most hosts scan `.agents/skills` (project) or `~/.agents/skills` (user):

```sh
python3 ~/src/10x-swe/scripts/hosts.py link agents --dest ~/.agents      # or .agents in a project
```

Or point your host at `plugins/10x-swe/skills` directly. Commands and agents are
host-specific and are not linked.

### Accounts, keys and costs

- **Running an agent** costs whatever that agent costs (table above). opencode's free
  models are the zero-cost path; nothing in this repository needs a paid account.
- **Skills that call paid services or external tools** are listed in the plugin's
  [requirements table](plugins/10x-swe/README.md#skills-that-need-accounts-keys-or-external-tools)
  (for example `web-research` needs a search API key, `x-api` needs X API credentials,
  `gemini` needs a Google sign-in). Everything else runs locally.
- **Optional MCP servers** are listed in [examples/mcp.optional.json](plugins/10x-swe/examples/mcp.optional.json);
  some need their own keys.
- **The playground** needs a Docker account: Docker Sandboxes requires a Docker
  sign-in for local use (`./playground doctor` tells you if it is missing).
- **distiller EPUB covers** call the paid Muse image API only when you export
  `DISTILLER_MUSE_API_KEY`; pass `--cover PATH` to avoid it.

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
When a build check fails, `plan` and `setup` print a one-line `fix`:

| OS | Fix |
|---|---|
| Debian/Ubuntu | `sudo apt-get update && sudo apt-get install -y build-essential pkgconf libssl-dev golang` |
| Fedora | `sudo dnf install -y gcc pkgconf-pkg-config openssl-devel golang` |
| macOS | `xcode-select --install; brew install pkg-config openssl go rustup` |
| Rust older than 1.88 (distro packages often are) | install [rustup](https://rustup.rs), then `rustup update stable` |

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

The default prefix is `$AGENT_KNOWLEDGE_HOME` when set, otherwise
`~/.local/share/10x-swe/knowledge`; `doctor` prints the path it checked. For isolation,
append `--prefix "/absolute/new/path"` to plan, setup and doctor. Use the same path for
all three. Activate its `env.sh` in each new shell; setup
does not edit shell profiles or configure your agent harness.

| Symptom | Next step |
|---|---|
| Missing build prerequisite or dependency build failure | Run the printed `fix:` command (or install the stated prerequisite), then rerun setup against the same prefix and unchanged checkout |
| No completed installation receipt | Check the path doctor printed; point `--prefix` or `AGENT_KNOWLEDGE_HOME` at the prefix you set up, or fix the original setup error and rerun setup |
| `skill-search` is not found | Source the printed `env.sh` in the current shell, then check `command -v skill-search` |
| `env.sh` is missing | Rerun setup with the same source and prefix; it restores activation and prints the next step |
| Prefix was built from a different source revision | Keep the old prefix and build this revision into a fresh one with `--from OLD_PREFIX` (see below) |
| Local graph is stale after an intentional skill change | Run `skill-search refresh --lexical` and retry discovery |

Default data stores live inside the prefix. To upgrade after `git pull`, build into a
fresh prefix and carry your library, bookmarks and session index over, then activate
the new `env.sh`:

```sh
./knowledge setup --prefix ~/.local/share/10x-swe/knowledge-NEW --from "$AGENT_KNOWLEDGE_HOME"
```

`--from` copies only `knowledge/sources` and `state`; the old prefix is left intact,
so reactivating its `env.sh` switches back. Untracked and ignored files in your clone
(for example a skill's `node_modules`) do not count as source changes. Explicitly
configured library or index paths outside the prefix are not moved. See
[setup and recovery](https://github.com/cercova-studios/10x-swe/wiki/Getting-started).

### Optional recoverable playground

Choose this route when you want a private Linux microVM with Nix-pinned tools and
host-held checkpoints. It requires Python 3.11+, Docker Sandboxes 0.48.0 and a Docker
account sign-in.
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

## Host compatibility

| Host | Status | Skills | Agents | Commands | Hooks/MCP | How it loads |
|---|---|---|---|---|---|---|
| [Claude Code](https://code.claude.com/docs/en/plugins-reference) | Supported | ✓ | ✓ | ✓ | MCP example only | `.claude-plugin/` (canonical) |
| [Codex CLI](https://developers.openai.com/codex/plugins) | Supported (skills) | ✓ | – not supported by Codex plugins | – | MCP example only | generated `.agents/plugins/marketplace.json` + `.codex-plugin/` |
| [Grok Build](https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-pager/docs/user-guide/09-plugins.md) | Supported | ✓ | ✓ | ✓ | MCP example only | reads `.claude-plugin/` |
| [Copilot CLI](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-plugin-reference) | Partial | ✓ | unverified | unverified | MCP example only | `.github/plugin/marketplace.json` → `.claude-plugin/` |
| [opencode](https://opencode.ai/docs/skills/) | Supported via link | ✓ | ✓ translated | ✓ | manual | `scripts/hosts.py link opencode` |
| [pi](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/packages.md) | Partial | ✓ | – no subagents | ✓ prompt templates | manual | root `package.json` |
| [Agent Skills hosts](https://agentskills.io/specification) | Skills | ✓ | – | – | – | `scripts/hosts.py link agents` |

### For maintainers

`.claude-plugin/marketplace.json`, each `plugins/*/.claude-plugin/plugin.json` and the
skill frontmatter are the source of truth. After adding or renaming a skill, agent or
command, link it in the [plugin catalog](plugins/10x-swe/README.md#maintaining-the-catalog)
and run `python3 scripts/hosts.py sync`; it regenerates the Codex and pi adapters and
the skill-requirements table. `python3 scripts/validate.py` and
`tests/test_plugin_metadata.py` run the same checks as CI. Bump the plugin
`version` with every user-visible change: Claude Code, Codex and Grok only update
installed plugins when it changes.

## Documentation

[Guides and examples](https://github.com/cercova-studios/10x-swe/wiki) · [Tool capabilities](plugins/knowledge/README.md) · [Skill catalog](plugins/10x-swe/README.md) · [Architecture](ARCHITECTURE.md) · [Help and issues](https://github.com/cercova-studios/10x-swe/issues)

## License

[MIT](LICENSE). Bundled tools and skills retain their upstream licenses and credits.
Maintained by [Rohit Nair](https://github.com/rnair98).
