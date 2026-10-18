# Using jj as a coding agent

Read this before you commit, bookmark, push, or undo in a jj repository.
Commands are checked against jj 0.46.

Sources: [Using JJ With Coding Agents](https://minimallysufficient.com/ephemera/using-jj-with-coding-agents/)
(Minimally Sufficient, 2026-06-21) for the review-once workflow and
workspaces; [Towards an AI-Native Development Workflow](https://ianbull.com/posts/jj-vibes/)
(Ian Bull, 2025-12-09) for the plan/apply/curate loop and intent capture; the
rest comes from mistakes observed in agent sessions.

## 1. Read the repository's own contract first

A repository that uses jj usually documents how it wants changes shaped:
`CONTRIBUTING.md`, `AGENTS.md`, or `just`/`make` recipes. Read the whole
section before your first jj write. Repository rules override this file.

Look for:

- the trunk bookmark (for example `main` or `dev`) and the remote it tracks;
- whether changes go on a feature bookmark, and how it is named;
- the push and pull-request command (for example a `just stack` recipe);
- checks that replace commit hooks, since jj does not run Git hooks.

Do not use raw `git add`, `git commit`, or `git push` in a colocated repo
unless the user asks. Git writes bypass the jj workflow and leave jj to
import the result.

## 2. Pick the right bookmark; never move a trunk on your own

A bookmark's role depends on the open pull requests, not only on its name. A
branch can be the base for feature PRs *and* the head of a release PR (for
example `dev` → `main`). Before choosing where a commit goes, check:

```bash
gh pr list --head <bookmark>    # is this bookmark the head of an open PR?
gh pr list --base <bookmark>    # do feature PRs target it?
```

- If the user says the work belongs in an existing PR, move that PR's head
  bookmark forward to your commit (`jj bookmark set <head> -r <change>`) and
  push it. Moving forward only adds commits; it never rewrites pushed ones.
- Otherwise, put your work on a feature bookmark:

```bash
jj new trunk()                       # or the repo's trunk, e.g. dev@origin
# ...edit...
jj commit -m "why this change exists"
jj bookmark create feat/short-name -r @-
```

- Bookmark `@-` (the finished commit), not `@` (the empty working copy).
- Do not move or push a trunk or PR-head bookmark unless the user asks.
  Never move one backwards or sideways (`--allow-backwards`) after it is
  pushed: that rewrites what an open PR shows.
- If a push fails with `Non-tracking remote bookmark <name>@origin exists`,
  run `jj bookmark track <name>@origin` once, check that your local bookmark
  is a descendant of the remote one, then push again.
- Before reporting state, compare local and remote:
  `jj log -r '<trunk>@origin::@'`. If the remote moved unexpectedly, report
  it. Do not push or rewrite over it.

## 3. Plan, apply, curate: one change per plan step

Agree on a plan before generating code. Then implement it one step at a time,
each step in its own change, and shape the history only at the end.

**Plan.** Clarify the problem, edge cases, and steps with the user. Write no
code yet.

**Apply.** For each plan step:

```bash
jj new -m "step 2/4: parse denylist keys

Intent: <the request or prompt that drove this step, summarized>"
# implement only this step; edits are snapshotted into this change
# review the diff (jj diff) and run the relevant tests
```

The description holds the intent while you work. It is mutable, travels with
the change through rebases and squashes, and is never a file in the tree.
That makes it better than writing temporary intent files: in jj every new
file is tracked automatically, so a forgotten `INTENTS-*.md` file gets pushed.

**Curate.** Before the stack leaves your machine, reshape it so commits match
ideas, not the order files were edited: `jj split`, `jj squash`,
`jj rebase -r <change> -A <change>` to reorder. Then rewrite each description
into a short narrative message. Keep the intent's *why*; drop raw prompt
text, internal notes, and anything sensitive, unless the repo asks for prompt
provenance in commits.

Split the work into reviewable chunks as you go:

```bash
jj commit -m "checkpoint: parser"     # finish a logical chunk, keep going on top
jj split -r <change-id> path/a path/b # split an over-large chunk by path
```

Each chunk should make sense on its own, so a human can review it while the
next one is being written.

Mutable history ends at the trunk. jj marks trunk and its ancestors
immutable (`immutable_heads()`) and refuses to rewrite them without
`--ignore-immutable`. Never pass that flag without the user's explicit
instruction.

## 4. Review once; make throwing work away cheap

The model writes code faster than a person can read it. Design the history so
each piece is reviewed once:

- The human reviews older checkpoints while the agent works on newer ones.
- Fixes and TODOs go in as commits on a side branch, then get squashed into
  the commit they belong to:
  `jj squash --from <fix> --into <target>`.
- For small follow-up fixes (typos, a missed import), `jj absorb` moves each
  hunk into the mutable ancestor that last touched those lines. Inspect the
  result with `jj log -p` before you continue.
- Conflicts are recorded in commits and don't block other operations. A
  rebase that leaves a conflicted commit is a state you can resolve later,
  not a failure. Report conflicted commits explicitly.
- If an approach is wrong, abandon it and start again. Don't repair it line
  by line: `jj abandon <change-id>` (descendants rebase onto its parent).
- To explain an older change, for a review or to suggest tests, read it with
  `jj show <change-id>`. Its description gives the intent and its diff
  gives the effect.

Do not abandon, squash, or rewrite commits the user or another agent owns,
or commits already pushed, without asking.

## 5. Parallel agents: one workspace each

In jj, every command snapshots *all* changes in the working directory into
`@`. If two agents share one directory, each one's edits land in the other's
commit. Git's "stage explicit paths" rule does not protect you here.

- Give each agent its own workspace:

  ```bash
  jj workspace add ../repo-agent-b --name agent-b -r <base>
  jj workspace list
  jj workspace forget agent-b        # when done; then delete the directory
  ```

- Workspaces share one repo and operation log, so every agent sees the
  others' commits immediately. That also makes them good for trying out
  ideas: start several approaches in separate workspaces, compare them
  directly with `jj diff --from <change-a> --to <change-b>`, keep the best
  one, and abandon the rest.
- If you are forced to share a directory, commit only your paths with
  `jj commit <paths> -m "..."` and leave the rest in the working copy.
- "Working copy is stale" means another workspace rewrote your base. Run
  `jj workspace update-stale`.

## 6. Undo carefully in a shared repo

`jj undo` reverts the *last operation in the repo*, which may belong to
another agent. Before undoing:

```bash
jj op log --limit 5           # confirm the top operation is yours
jj op revert <operation-id>   # revert one specific operation
jj op restore <operation-id>  # roll the whole repo back to that point
```

Use `jj op restore` only with the user's agreement when other agents are
active.

## 7. Before you finish

```bash
jj st
jj log -r '<trunk>@origin::@'
```

Report the change IDs and bookmarks you created, any conflicted commits,
whether anything was pushed, and the exact command that would push or open
the pull request. Push only when the user asks.
