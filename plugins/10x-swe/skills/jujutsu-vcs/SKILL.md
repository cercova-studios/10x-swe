---
name: jujutsu-vcs
description: Guide AI agents to use Jujutsu (jj) for version control. Covers core concepts, daily workflows, Git compatibility, conflict resolution, and collaboration with GitHub. Use this skill when working with jj repositories or when the user wants to use Jujutsu instead of Git.
---

<essential_principles>

Before you commit, bookmark, push, or undo, read the
[coding-agent workflow](references/coding-agents.md). Repository policy takes
precedence. Use one workspace per agent, inspect open PRs before selecting a
bookmark, and check the operation log before undoing shared history.

**Jujutsu (jj) is a Git-compatible VCS that eliminates common Git pain points.** It's designed for safety, simplicity, and powerful history manipulation.

**1. Working Copy Is Always a Commit**

Unlike Git, your working copy state is always a commit in jj. Every file change is automatically tracked in the current commit—no staging area, no `git add`. When you run most jj commands, changes are auto-committed.

```bash
# In Git: edit → add → commit
# In jj:  edit → done (auto-committed)
```

**2. Change IDs vs Commit IDs**

Every commit has two identifiers:
- **Change ID**: Stable across rewrites (use this daily)
- **Commit ID**: Changes when commit is rewritten (like Git's SHA)

Use change IDs in your workflow—they survive rebases and amends.

**3. Operations Are Always Reversible**

The operation log records every action. Made a mistake? `jj undo` reverses it. Need to see what happened? `jj op log` shows everything.

**4. Conflicts Are First-Class**

Conflicts don't block operations. They're recorded in commits and can be resolved later. No more "rebase in progress" states.

**5. Automatic Rebasing**

When you edit a commit, all descendants automatically rebase on top of the modified version. Bookmarks and working copy update automatically.

</essential_principles>

<quick_reference>

**Essential Commands:**
| Task | Command |
|------|---------|
| Status | `jj st` |
| Diff | `jj diff` |
| Log | `jj log` |
| Describe commit | `jj describe -m "message"` |
| Create new commit | `jj new` |
| Squash into parent | `jj squash` |
| Edit any commit | `jj edit <change-id>` |
| Undo last operation | `jj undo` |

**Working with Git repos:**
```bash
# Clone
jj git clone <url>

# Init in existing Git repo (colocated)
jj git init --colocate

# Fetch and push
jj git fetch
jj git push
```

</quick_reference>

<intake>
**What would you like to do with Jujutsu?**

1. Get started (clone, init, basic setup)
2. Make changes (daily development workflow)
3. Work with history (edit, split, squash, rebase)
4. Resolve conflicts
5. Collaborate (GitHub, push, pull, PRs)
6. Recover from mistakes (undo, operation log)
7. Understand a concept or command

**Wait for response before proceeding.**
</intake>

<routing>
| Response | Workflow |
|----------|----------|
| 1, "start", "clone", "init", "setup" | `workflows/getting-started.md` |
| 2, "change", "edit", "commit", "develop", "daily" | `workflows/make-changes.md` |
| 3, "history", "rebase", "split", "squash", "amend" | `workflows/work-with-history.md` |
| 4, "conflict", "merge", "resolve" | `workflows/resolve-conflicts.md` |
| 5, "github", "push", "pull", "pr", "collaborate", "remote" | `workflows/collaborate-github.md` |
| 6, "undo", "mistake", "recover", "oops", "operation" | `workflows/recover-mistakes.md` |
| 7, "concept", "understand", "what is", "how does" | Route to relevant reference file |

**After reading the workflow, follow it exactly.**
</routing>

<verification_loop>

After every operation, verify state:

```bash
# 1. Check current state
jj st

# 2. View recent history
jj log -r 'ancestors(@, 5)'

# 3. If issues, check operation log
jj op log
```

Report to user:
- Current commit and its description
- Any conflicts present
- Any pending changes

</verification_loop>

<reference_index>

**Core Knowledge** in `references/`:

| File | Contents |
|------|----------|
| core-concepts.md | Working copy, change IDs, automatic rebasing |
| git-command-mapping.md | Git → jj command translation table |
| revsets.md | Selecting commits with the revset language |
| bookmarks.md | Named pointers (like Git branches) |
| common-patterns.md | Typical workflows and patterns |
| troubleshooting.md | Common issues and solutions |

</reference_index>

<workflows_index>

**Workflows** in `workflows/`:

| File | Purpose |
|------|---------|
| getting-started.md | Initialize repos, clone, basic setup |
| make-changes.md | Daily development workflow |
| work-with-history.md | Edit, split, squash, rebase commits |
| resolve-conflicts.md | Handle and resolve conflicts |
| collaborate-github.md | Push, pull, PRs, remote workflows |
| recover-mistakes.md | Undo operations, restore state |

</workflows_index>

<success_criteria>

A successful jj operation:
- Completes without unexpected conflicts
- Maintains clean history (descriptive commit messages)
- Keeps working copy in expected state
- Can be undone if needed via `jj undo`

</success_criteria>
