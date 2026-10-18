---
name: browser-use
description: Automates browser interactions for web testing, form filling, screenshots,
  and data extraction. Use when the user needs to navigate websites, interact with
  web pages, fill forms, take screenshots, or extract information from web pages.
allowed-tools: Bash(browser-use:*)
metadata:
  skill-graph-id: plugin/10x-swe/browser-use
  skill-graph-uses: ''
  skill-graph-used-by: ''
---

# Browser Automation with browser-use CLI

Use the CLI for browser navigation, testing, screenshots, forms, and extraction when permitted by the active harness. Use the harness's required browser surface if it specifies one. This skill does not authorize installation, external data transfer, delegation, or user-facing submissions.

## Choose the browser and session

- `chromium`: isolated browser; headless by default, `--headed` for visible debugging.
- `real`: local Chrome. Before opening, ask which profile to use or whether to use a fresh browser; list candidates with `browser-use -b real profile list`. Honor an already explicit profile choice.
- `remote`: Browser-Use Cloud; requires `BROWSER_USE_API_KEY`. Use only when cloud access and the data sent there are authorized.

Commands reuse a persistent session. Choose `--session NAME` to separate work and keep that name on subsequent commands.

## Inspect, act, verify

```bash
browser-use --session task open https://example.com
browser-use --session task state
browser-use --session task input 3 "text"
browser-use --session task click 5
browser-use --session task state
browser-use --session task screenshot result.png
browser-use --session task close
```

Indices above are examples: obtain real indices from the current `state` output. Refresh state after navigation or page changes. Verify the requested result in page state or screenshots; an accepted command alone does not establish success.

## Sensitive workflows

Before syncing local cookies to cloud, ask for the local profile and specific domains, then obtain confirmation. Never default to the full profile. Create a new cloud profile per domain sync unless the user selects an existing one. Full-profile sync requires explicit need and authorization.

Use existing protected key configuration; do not print secrets or place them in command arguments or shell history. The archived reference includes key and cookie examples that must be adapted to these rules and the active harness's requirements.

Cloud `run` tasks and `extract` use model services. For an authorized remote task, bound scope and steps, retain task/session IDs, and inspect `task status <id>` before expanding logs. Launch parallel tasks only when delegation is authorized. A completed task can leave its session running.

## Progressive reference

Read only the matching section of [CLI reference](references/cli-reference.md) for commands, setup, Python sessions, cloud tasks/profiles, cookie sync, or tunnels. It preserves the previous catalog verbatim; verify installed CLI flags with help before relying on version-sensitive options.

Run `browser-use doctor` for startup failures. Do not install or reset unrelated sessions automatically. Public session sharing and tunnels expose content or local services; obtain required authorization before using them.

## Cleanup and reporting

Close sessions created for this task. Stop owned cloud sessions and tunnels separately: tunnels survive browser closure. Avoid `--all` cleanup when other work may be active. Report the observed result, saved artifacts, and any pending verification.
