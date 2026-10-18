---
name: gh-cli
description: GitHub CLI (gh) comprehensive reference for repositories, issues, pull
  requests, Actions, projects, releases, gists, codespaces, organizations, extensions,
  and all GitHub operations from the command line.
metadata:
  skill-graph-id: plugin/10x-swe/gh-cli
  skill-graph-uses: ''
  skill-graph-used-by: ''
---

# GitHub CLI

Use `gh` for GitHub repository metadata, issues, pull requests, Actions, and API operations. Select the smallest command that handles the request. The bundled examples target gh 2.85.0 (January 2026); verify current syntax with the installed CLI.

## Start with context

1. Check `gh --version` and the relevant command's `--help`.
2. Confirm the target repository, host, and account. Use explicit repository/hostname selectors supported by that command when ambient context is ambiguous.
3. Inspect authentication with `gh auth status`. Use existing secure authentication. Do not print tokens with `gh auth token` or `--show-token`, or enable insecure storage.
4. Read current state before mutations. User authorization and repository policy still govern comments, reviews, merges, dispatches, releases, deletion, secrets, scopes, and account changes.

Do not install `gh`, extensions, or alter credential helpers merely to consult this reference. If required capability is missing, report it and use an authorized alternative.

## Load only the command family needed

| Task | Reference |
|---|---|
| Authentication, environment, configuration, or shell integration | [Setup](references/setup.md) |
| Repository creation, cloning, metadata, forks, or settings | [Repositories](references/repositories.md) |
| Issue search, metadata, creation, or edits | [Issues](references/issues.md) |
| PR creation, review, diffs, checks, checkout, or merge | [Pull requests](references/pull-requests.md) |
| Runs, workflows, caches, secrets, or variables | [Actions](references/actions.md) |
| Projects, releases, and assets | [Projects and releases](references/projects-and-releases.md) |
| Search, gists, Codespaces, labels, keys, rulesets, extensions, or attestations | [Other commands](references/other-commands.md) |
| REST/GraphQL calls or structured formatting | [API and output](references/api-and-output.md) |
| Multi-step examples | [Workflow examples](references/workflow-examples.md) |

These references preserve the original examples, including outdated or unsafe patterns. Treat them as discovery aids. The command's current `--help` and [official manual](https://cli.github.com/manual/) determine supported flags; [GitHub API docs](https://docs.github.com/en/rest) determine API behavior.

## Produce reviewable results

- Prefer supported `--json` fields and `--jq` for structured reads. Bound lists and deliberately handle pagination. Flags are command-specific; an API flag is not automatically valid on `issue list` or `pr list`.
- Use body/notes files for multiline content to preserve exact text and avoid shell expansion.
- Inspect the working tree before checkout or PR work. Stage only owned paths; examples using `git add .` are not permission to collect others' changes.
- Before publishing or merging, verify the intended target, final content, and applicable checks. Do not bypass checks with administrator options without explicit authorization.
- Preview and bound bulk operations. Confirm irreversible deletion or security changes and prepare rollback where possible. Keep secrets out of command arguments, logs, generated reports, and committed files.
- After a write, inspect the resulting resource. A workflow dispatch is not a completed run; confirm its actual status and conclusion. On an uncertain response, inspect current state before repeating a write.

Report the resulting URL or identifier, performed checks, and unresolved failures. Attach created PRs using the active client’s required artifact tool.
