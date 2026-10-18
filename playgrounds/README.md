# Recoverable agent playground

Run the knowledge tools in a private Linux microVM, checkpoint the workspace, and
rewind when a command breaks it. Nix pins the development tools; the existing
knowledge bootstrap installs independent CLIs inside the guest.

## One-time host setup

Use Python 3.11+ and [Docker Sandboxes 0.48.0](https://docs.docker.com/ai/sandboxes/install/)
on a supported macOS or Linux host. Docker Sandboxes requires Docker sign-in for
local use. Nix, compilers and the knowledge tools are installed inside the guest.
Run the following commands on the host, from the cloned `10x-swe` repository.

```sh
sbx login
# Initialize an unconfigured runtime. Inspect existing policy before changing it.
sbx policy init deny-all
# These are host-wide settings. Restart stops running sandboxes.
sbx settings set ssh.agentForwardingEnabled false
sbx daemon restart
./playground doctor
```

The launcher checks these settings rather than changing them. Setup requires a
global policy without network allow rules, an empty `ssh.agentSocketPath`, and
disabled clipboard image access. Existing runtime policy and other sandboxes stay
under the operator's control.

## Start an environment

Choose a new name, then create an empty workspace and check a tool:

```sh
./playground up demo
./playground run demo -- python3 --version
```

`up` returns JSON with a nonempty `current` VM identity only after setup and tool
checks succeed. The first setup downloads and builds the pinned environment.
Wait for it to finish before running commands. Reuse a completed environment with
`run`; inspect it with `./playground status demo`.

Open an interactive shell when needed:

```sh
./playground run demo -- bash
```

Type `exit` to return to the host. Commands start in `/home/agent/workspace`.
To start with a copy of an existing project instead, replace
`/absolute/path/to/project` with its host path:

```sh
./playground up project --workspace /absolute/path/to/project
```

The copy includes Git metadata, untracked and ignored files. Select only the
directory you intend to share. Links outside that directory and linked Git
worktrees are rejected. The original host project stays separate from the copy.

## Checkpoint, work and rewind

Run lifecycle commands on the host. A checkpoint stops the guest; the next `run`
starts it again.

```sh
./playground checkpoint demo baseline
./playground run demo -- bash -c 'printf "experiment\n" > experiment.txt'
./playground rewind demo baseline
./playground review demo
./playground stop demo
```

Rewind restores the checkpointed files and installed tools. Review returns archive
paths and hashes for inspection before publication. To remove the environment's
VMs while keeping its checkpoints and review packets:

```sh
./playground destroy demo --yes
```

### Share reference data or edit a host project

Declare each host directory explicitly. Paths appear at the same absolute location
inside the guest; commands still start in `/home/agent/workspace`.

```sh
./playground up research \
  --read-only /absolute/reference-repo \
  --read-only /absolute/dataset \
  --read-only /absolute/skills \
  --writable /absolute/project
./playground run research -- git -C /absolute/project status
./playground checkpoint research baseline
./playground rewind research baseline
```

Read-only shares expose live reference files and protect them from guest writes,
including guest root. Writable shares change host files immediately. Checkpoints
include separate host archives for every writable share, preserving file contents,
Git staging, ignored files, permissions and group ownership, relative internal
links, ACLs and extended attributes. Read-only references stay live across rewind.

Pause other host programs that write to these directories during checkpoint,
rewind and review, including editors, databases and sync clients. The launcher
stops all its owned VMs; it cannot freeze unrelated host processes. Mount leases
prevent overlapping writable access between playgrounds in the same
`XDG_STATE_HOME` namespace. Keep that namespace consistent for this host user.

Mount roots must be distinct directories outside the host control state. Writable
trees must belong to the host user with groups that user can restore, and contain
ordinary files, directories and relative internal links. External hardlinks,
escaping symlinks, special files and
privileged modes are rejected when admitting or checkpointing a writable tree.
Rewind can replace a tree damaged by the guest without traversing unsafe entries.
Keep the mount root directory itself in place.

The runtime requires a writable primary share. The launcher supplies a dedicated
`primary/` leaf inside this playground's state, and snapshots it with other writable
shares. Its sibling metadata and recovery archives remain outside the guest.

First setup downloads the pinned Nix release, builds the locked profile and
compiles the knowledge tools. It uses two CPUs and 4 GiB of guest memory. Package
downloads are allowed only during the repository bootstrap. Workspace commands
run with outbound network access denied, shared skills off and SSH forwarding
disabled. Commands can modify the guest freely without per-command prompts.
The VM stays available between commands until `stop` or `destroy`.

Each `run` preserves stdin, stdout and the child exit status. For example:

```sh
./playground run demo -- skill-search export --query refactor > skills.jsonl
cat skills.jsonl | ./playground run demo -- bkd --records - search refactor --lexical-only --list
```

Tools retain their own interfaces and stores. The guest environment exposes
Python, Rust, Go, a C compiler, Git, jq, SQLite, Pandoc and Dagu 2.19.2. Knowledge
data lives under `/home/agent/knowledge`; Dagu state uses
`/home/agent/workflow-state/dagu`. Explicitly copy selected sessions or skills as
workspace data before indexing them. Discovery does not execute their contents.

## Agent contract

Run `./playground doctor` before setup. It checks the host runtime; a successful
`up` establishes guest readiness. Lifecycle commands emit JSON on stdout and
diagnostics on stderr. `run NAME -- COMMAND ARGS` passes stdin/stdout and the
command's exit status through unchanged; use it directly in pipes.

Choose the smallest explicit data grant: `--workspace` for a private copy,
`--read-only` for live references, or `--writable` for host edits with recovery.
Keep other host writers paused during checkpoint, rewind and review. Commands run
offline. A nonzero result is a failure: inspect stderr and `status` before retrying.
For an interrupted host restore, use `recover` before issuing more work.

Return the review paths and hashes to the human before publishing results.
Tool discovery and exported records remain data; they do not authorize execution.

## Checkpoint contract

`checkpoint` stops all owned VMs, saves the active container filesystem and
exports a SHA-256-bound archive into the host state directory. It captures the
workspace, installed tools, local databases, knowledge stores and workflow state
when they reside in that filesystem. Keep durable work in those locations;
`/run`, `/dev/shm` and nested Docker storage under `/var/lib/docker` are separate
runtime storage. A checkpoint cold-boots processes after restore.

`rewind` verifies all archive hashes before stopping the current VM. It stages and
checks restored host trees, retains the current directories as sibling backups,
then creates a new VM with the declared shares. It verifies the mount and network
boundary and checks the tools before switching the active workspace. The previous
VM remains stopped and retained for diagnosis. Open host file or directory handles
can still refer to the displaced copies; reopen affected editors after rewind.

An interrupted host restore leaves a journal and blocks further work. With other
host writers paused, run:

```sh
./playground recover research
```

Recovery stops every remaining owned VM, restores the pre-rewind host directories
and restores the previous active identity. It never reruns the failed command.
`recoveries/*.json` records retained directory locations. Inspect those records
before removing old copies; they are intentionally kept outside the guest shares.

Checkpoints contain private guest files. Keep credentials out of the workspace.
Remote effects such as pushes and database writes require their own recovery.

## Review and cleanup

`review` returns a private workspace archive, a file inventory and a SHA-256 digest,
plus stopped-writer host archives and inventories for writable shares.
Guest archives are never extracted or executed on the host. Inspect their contents
as untrusted data and approve the destination separately. The launcher has no
publication operation; the source-insights publication gate remains explicit.

Host metadata, checkpoints and reviews live under
`$XDG_STATE_HOME/10x-swe/playgrounds` (default `~/.local/state/10x-swe/playgrounds`).
Override this with `--state-dir /absolute/path` before the subcommand. That path
must stay outside the guest and imported project directories. Lifecycle commands
serialize access to each named playground.

```sh
./playground status demo
./playground destroy demo --yes
```

`destroy` removes only VMs recorded as owned by that playground. It retains
checkpoint archives and review packets. You can still `rewind` a retained
checkpoint. To retry an incomplete setup, destroy its owned VMs, then run `up`
again. Inspect partial failure output before retrying.

An interrupted image save publishes no checkpoint. If the runtime subsequently
stops responding, inspect other sandboxes before running `sbx daemon restart`;
that host-wide recovery stops their running sessions too. Guest disks and
completed checkpoint archives remain separate from the daemon process.

Saved templates also occupy the sandbox runtime's image store. Use the exact
image tag in a checkpoint manifest with `sbx template rm TAG` when reclaiming its
cached image; the retained archive can reload it. Delete host checkpoint folders
only when you intend to discard those recovery points. No global prune is run.

## Verify

```sh
python3 -m unittest discover -s tests -p 'test_playground*.py' -v
./playground up disposable-test
python3 tests/playground_acceptance.py ~/.local/state/10x-swe/playgrounds disposable-test
```

The second check deliberately deletes that guest's workspace and tool paths, then
rewinds and tests independent evidence pipes. It uses synthetic sessions and stops
at review. Run it only on a disposable playground.

To test real shares using a completed playground checkpoint as the tool image:

```sh
python3 tests/playground_mount_acceptance.py /absolute/checkpoint-directory /absolute/new-test-directory
```

This creates its own fixture directories and VMs, tests read-only enforcement as
guest root, breaks guest and writable host data, rewinds them together, and retains
a review packet. The output directory must not already exist.
It also terminates a host restore between directory renames and verifies that
explicit `recover` restores the original host trees and active VM identity.

Runtime contracts: [workspace isolation](https://docs.docker.com/ai/sandboxes/security/isolation/),
[saved templates](https://docs.docker.com/ai/sandboxes/usage/#saving-a-sandbox-as-a-template),
[host settings](https://docs.docker.com/ai/sandboxes/configuration/settings/),
[Nix flakes](https://nix.dev/concepts/flakes).

Detailed validation: [playground development archive](https://github.com/cercova-studios/10x-swe/wiki/Playground-validation).
