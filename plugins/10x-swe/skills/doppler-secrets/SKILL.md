---
name: doppler-secrets
description: Use the Doppler CLI to access and manage secrets safely in both ad hoc scripts and long-lived projects. Covers CLI install, env injection, project binding via doppler.yaml, environments, service tokens, Docker, Kubernetes, and CI/CD integration. Use when a task touches secrets and must avoid exposing them in logs, prompts, command history, or tool output.
compatibility: Requires the Doppler CLI and a Doppler account (DOPPLER_TOKEN or doppler login).
---

<objective>
Provide a single, authoritative workflow for using the Doppler CLI to handle secrets safely across ad hoc scripting and long-lived projects.
</objective>

<essential_rules>
1) Doppler CLI only.
- Never use the Doppler MCP for secret access.
- Use the `doppler` CLI for all reads, writes, validation, and runtime injection.

2) Never expose secret values.
- Never print secrets to stdout/stderr.
- Never include secret values in LLM/tool message bodies, prompts, or files.
- Never serialize secrets into files, stack traces, debug dumps, or shell history.
- When commands carry tokens, set `export HISTIGNORE='doppler*:export DOPPLER_TOKEN*'` first.

3) Prefer env injection over value retrieval.
- Primary pattern: `doppler run --project=<p> --config=<c> -- <command>`.
- Application reads injected env vars internally.
- Avoid `doppler secrets get` / `doppler secrets download` unless strictly required, and never log the output.

4) Bind repos with a committed `doppler.yaml`.
- Project-root `doppler.yaml` lets `doppler setup --no-interactive` work for teammates and CI.
- Per-user state lives in `~/.doppler/.doppler.yaml` and must NOT be hand-edited.
</essential_rules>

<step_0_install_hedge>
Always check the CLI is installed before any other step. If missing, install via the OS-appropriate method below, then re-check.

Detection:
```bash
if ! command -v doppler >/dev/null 2>&1; then
  echo "doppler CLI missing — installing" >&2
  # run an install branch from the table below
fi
doppler --version
```

OS-specific install (use the first matching branch):

- macOS (Homebrew):
  ```bash
  brew install dopplerhq/cli/doppler
  ```

- Linux — Debian/Ubuntu (apt, signed repo, persistent):
  ```bash
  sudo apt-get update
  sudo apt-get install -y apt-transport-https ca-certificates curl gnupg
  curl -sLf --retry 3 --tlsv1.2 --proto "=https" \
    'https://packages.doppler.com/public/cli/gpg.DE2A7741A397C129.key' \
    | sudo gpg --dearmor -o /usr/share/keyrings/doppler-archive-keyring.gpg
  echo "deb [signed-by=/usr/share/keyrings/doppler-archive-keyring.gpg] https://packages.doppler.com/public/cli/deb/debian any-version main" \
    | sudo tee /etc/apt/sources.list.d/doppler-cli.list
  sudo apt-get update && sudo apt-get install -y doppler
  ```

- Linux — RHEL/CentOS/Fedora (yum/dnf):
  ```bash
  sudo rpm --import 'https://packages.doppler.com/public/cli/gpg.DE2A7741A397C129.key'
  curl -sLf --retry 3 --tlsv1.2 --proto "=https" \
    'https://packages.doppler.com/public/cli/config.rpm.txt' \
    | sudo tee /etc/yum.repos.d/doppler-cli.repo
  sudo dnf install -y doppler || sudo yum install -y doppler
  ```

- Linux/macOS fallback or CI — official install script:
  ```bash
  (curl -Ls --tlsv1.2 --proto "=https" --retry 3 https://cli.doppler.com/install.sh \
    || wget -t 3 -qO- https://cli.doppler.com/install.sh) | sh
  ```

- Windows (PowerShell, winget):
  ```powershell
  winget install doppler
  ```

- Docker / containers (no package manager): bake into the image — see `templates/Dockerfile.doppler.snippet`.

Authoritative sources (consult only if you suspect a stale flag):
- https://docs.doppler.com/docs/install-cli
- https://github.com/DopplerHQ/cli

After install, verify:
```bash
doppler --version
```
Do NOT proceed if the CLI is still missing — report the install failure and stop.
</step_0_install_hedge>

<quick_start>
1. Ensure CLI installed (see step 0).
2. `doppler login` (once per machine; opens browser).
3. In repo root: `doppler setup` to pick project + config (or commit a `doppler.yaml`).
4. Run code via `doppler run -- <command>`.
5. For non-interactive environments (CI, prod, containers): use a service token via `DOPPLER_TOKEN`.
</quick_start>

────────────────────────────────────────────────────────
PART A — AD HOC SCRIPTS
────────────────────────────────────────────────────────

<ad_hoc_workflow>

<step_1_preflight>
Verify CLI + auth:
```bash
command -v doppler >/dev/null || { echo "doppler CLI missing" >&2; exit 1; }
doppler configure debug >/dev/null 2>&1 || { echo "doppler not authed/configured" >&2; exit 1; }
```
</step_1_preflight>

<step_2_validate_required_names>
Validate secret names only — never values:
```bash
doppler secrets --project=<project> --config=<config> --only-names --json
```
Compare required names against this list. Do not retrieve values during validation.
</step_2_validate_required_names>

<step_3_execute_with_env_injection>
Preferred:
```bash
doppler run --project=<project> --config=<config> -- python /path/to/script.py
```
Multi-command:
```bash
doppler run --project=<p> --config=<c> --command="./configure && ./run; ./cleanup"
```
</step_3_execute_with_env_injection>

<step_4_safe_python_pattern>
See `templates/secure_python_with_doppler_cli_env.py`. Read env, never print secrets:
```python
import os, sys
required = ["X_OAUTH2_ACCESS_TOKEN"]
missing = [k for k in required if not os.getenv(k)]
if missing:
    print(f"Missing required secret env vars: {', '.join(missing)}", file=sys.stderr)
    raise SystemExit(1)
token = os.environ["X_OAUTH2_ACCESS_TOKEN"]  # use directly; never log
```
</step_4_safe_python_pattern>

<step_5_output_sanitization>
Allowed: counts, ids, timestamps, non-sensitive identifiers, summarized findings.
Forbidden: token strings, secret values, env dumps, full credentialed request dumps.
</step_5_output_sanitization>

</ad_hoc_workflow>

────────────────────────────────────────────────────────
PART B — PROJECTS / LONG-LIVED APPLICATIONS
────────────────────────────────────────────────────────

<project_workflow>

<step_1_bind_repo_to_project>
Run once per repo, in repo root:
```bash
doppler setup
```
This writes scope into `~/.doppler/.doppler.yaml` (per-user, never hand-edit).

For team-wide reproducibility, also commit a `doppler.yaml` at the repo root (see `templates/doppler.yaml`):
```yaml
setup:
  - project: my-app
    config: dev
```
Monorepo variant:
```yaml
setup:
  - path: backend/
    project: my-app-api
    config: dev
  - path: frontend/
    project: my-app-web
    config: dev
```
Teammates and CI then run:
```bash
doppler setup --no-interactive
```
</step_1_bind_repo_to_project>

<step_2_environments_and_configs>
Doppler hierarchy: `Workspace → Project → Environment (dev/stg/prd) → Config`.
- Branch configs (e.g. `dev_personal`) inherit from a root config (`dev`) and override per-developer.
- Promote secrets between environments via the dashboard (review/approval) rather than copy-paste.
- For new projects, bootstrap structure declaratively with `doppler-template.yaml` + `doppler import`. See https://docs.doppler.com/docs/project-templates.
</step_2_environments_and_configs>

<step_3_application_runtime>
Always launch the app under `doppler run`:
```bash
doppler run -- npm start
doppler run -- python -m myapp
doppler run -- ./bin/server
```
Do not call `doppler secrets download` to materialize a `.env` for the app at runtime if `doppler run` is viable.
</step_3_application_runtime>

<step_4_service_tokens_for_non_interactive>
Service tokens are read-only, scoped to a single project+config. Use them everywhere a human is not present (CI, prod, containers, VMs).

Create:
```bash
# interactive setup, then mint
doppler setup
doppler configs tokens create ci-deploy --plain

# or single-shot
doppler configs tokens create ci-deploy \
  --project my-app --config prd --plain
```
Ephemeral token (auto-expires):
```bash
DOPPLER_TOKEN=$(doppler configs tokens create job-$(date +%s) \
  --project my-app --config prd --max-age 5m --plain)
```
Revoke:
```bash
doppler configs tokens revoke -p my-app -c prd dp.st.prd.xxxx
```

Auth precedence (highest → lowest): `--token` flag → `DOPPLER_TOKEN` env → `--project/--config` flags → directory scope in `~/.doppler/.doppler.yaml`.
</step_4_service_tokens_for_non_interactive>

<step_5_ci_cd>
GitHub Actions example (token from repo secrets):
```yaml
- uses: dopplerhq/cli-action@v3
- env:
    DOPPLER_TOKEN: ${{ secrets.DOPPLER_TOKEN_PRD }}
  run: doppler run -- ./deploy.sh
```
Rules:
- Store the service token in the CI provider's secret store; never echo it.
- Use one token per environment (prd/stg/dev).
- Set `HISTIGNORE='export DOPPLER_TOKEN*'` in any shell that may be recorded.
</step_5_ci_cd>

<step_6_docker>
Pattern A — bake CLI into image, inject token at runtime (recommended):
```dockerfile
# see templates/Dockerfile.doppler.snippet for the full snippet
RUN (curl -Ls --tlsv1.2 --proto "=https" --retry 3 https://cli.doppler.com/install.sh) | sh
ENTRYPOINT ["doppler", "run", "--"]
CMD ["node", "server.js"]
```
Run:
```bash
docker run -e DOPPLER_TOKEN="$DOPPLER_TOKEN" my-app:latest
```

Pattern B — host-side injection (no Doppler in image):
```bash
doppler run -- docker compose up
```

Never `COPY .env` into an image. Never bake `DOPPLER_TOKEN` into a layer.
</step_6_docker>

<step_7_kubernetes>
Two supported approaches:

1) Doppler Kubernetes Operator (recommended) — syncs Doppler configs into native `Secret` objects; pods consume via `envFrom`. Install via Helm; see https://docs.doppler.com/docs/kubernetes-operator. The Operator handles rotation; no `doppler` binary in the image.

2) `doppler run` inside containers using `DOPPLER_TOKEN` from a K8s Secret:
```bash
kubectl create secret generic doppler-token \
  --from-literal=DOPPLER_TOKEN='dp.st.prd.xxxx'
```
```yaml
spec:
  containers:
    - name: app
      image: my-app:latest
      envFrom:
        - secretRef:
            name: doppler-token
```

Prefer (1) for production. Use (2) when the Operator is not available.
</step_7_kubernetes>

<step_8_local_env_hygiene>
- Do NOT commit `.env`, `.env.local`, `.env.*` (except `.env.example` containing names only).
- DO commit `doppler.yaml` (project binding) and `doppler-template.yaml` (project bootstrap).
- Add to `.gitignore`:
  ```
  .env
  .env.*
  !.env.example
  ```
- If a `.env` must be generated for a tool that cannot use `doppler run` (e.g. some IDEs):
  ```bash
  doppler secrets download --no-file --format env > .env
  ```
  Treat the file as ephemeral, ensure `.gitignore` covers it, and delete it after use.
- Pre-commit hooks: enable a secret scanner (gitleaks, trufflehog) to catch accidental commits.
</step_8_local_env_hygiene>

<step_9_rotation_and_history>
- View change history: `doppler secrets history SECRET_NAME` (or dashboard).
- Rotate via dashboard or integration (AWS/GCP/Azure rotation connectors).
- After rotation, restart consumers (apps re-read env at process start, not in-place).
- For automated rotation triggers, configure Doppler webhooks to ping your deploy/restart endpoint.
</step_9_rotation_and_history>

</project_workflow>

────────────────────────────────────────────────────────
COMMON FAILURES & FIXES
────────────────────────────────────────────────────────

<common_failures_and_fixes>
- `doppler: command not found` → run install hedge for the OS (step 0) and re-verify with `doppler --version`.
- Auth/config not initialized → `doppler login` (interactive) or set `DOPPLER_TOKEN` (non-interactive).
- "This token does not have access to requested config" → token scope mismatch; mint a new token for the correct project+config.
- Wrong secrets returned → check resolution with `doppler configure debug` and `doppler configure --scope $(pwd)`; confirm `doppler.yaml` matches the desired config.
- Secrets logged accidentally → strip debug prints, redact exceptions, never dump env or auth headers.
- Missing secrets at runtime → verify names exist in selected project/config (`doppler secrets --only-names`) and confirm the runtime is actually under `doppler run` or has `DOPPLER_TOKEN` set.
- Token leaked in shell history → rotate the token immediately (`doppler configs tokens revoke`), mint a new one, and set `HISTIGNORE` going forward.
</common_failures_and_fixes>

────────────────────────────────────────────────────────
VERIFICATION CHECKLIST
────────────────────────────────────────────────────────

<verification_checklist>
- [ ] `doppler --version` succeeds (CLI installed)
- [ ] Auth confirmed (`doppler configure debug` shows token source) OR `DOPPLER_TOKEN` set
- [ ] For projects: `doppler.yaml` committed; `.env*` ignored; `.env.example` (names only) optional
- [ ] Secret names validated without reading values
- [ ] Application launched via `doppler run` (or Operator-injected env)
- [ ] No secret output in logs/messages/files/shell history
- [ ] Service tokens scoped per environment; no human tokens in CI/prod
- [ ] Final response sanitized
</verification_checklist>

<success_criteria>
Agents reliably install, configure, and operate Doppler — for one-off scripts and long-lived projects — using CLI env injection and scoped service tokens, while preserving strict non-disclosure of secret values across all outputs.
</success_criteria>
