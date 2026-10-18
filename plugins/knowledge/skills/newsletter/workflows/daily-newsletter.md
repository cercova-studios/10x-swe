---
schema: workflow/v1
name: daily-newsletter
description: Produce an evidence-backed local AI newsletter with Dagu and seven-day retention.
skills:
  - global/newsletter
runner: workflows/daily-newsletter.yaml
resources:
  - workflows/daily-newsletter.yaml
  - scripts/newsletter.py
  - scripts/research.py
  - scripts/draft.py
  - assets/reader.html
  - assets/reader.css
  - assets/reader.js
---

# Daily newsletter

This optional Dagu 2.19.2 recipe runs daily at 08:00 America/Detroit. A running
scheduler is required. A 24-hour catch-up window with latest-only overlap handles
short downtime; it does not recreate every missed edition. Use an always-on host
if delivery at a specific wall-clock time is essential.

The steps are ordinary commands. Acquisition calls an explicit search command and
distiller's public stdin interface. Drafting and review use an optional Codex CLI
adapter; another producer can write the same JSON files. Rendering, validation and
retention have no model, search-provider or companion-tool imports. Nothing invokes
source-insights publication or reads a private knowledge database.

## Setup and first run

Requirements: Python 3.11+, Dagu 2.19.2, distiller, and an authenticated Codex CLI
supporting `exec --ignore-user-config --output-schema`. Provider keys belong in an
operator-owned local environment, outside Git. Inspect the configured public source
domains, search command, lookback and request limits before acquisition.

From the marketplace root, create a local configuration using
`assets/config.example.json`. Resolve the search script path from your checkout;
the helper is owned by the independent web-research skill. The example uses Exa;
Parallel can be added to `providers` and the helper's `-p` argument after a live
credential preflight. Missing or rejected keys fail visibly; there is no secret
discovery or implicit provider substitution.

The example searches 17 sections: frontier models; open models and local AI;
agents and coding; developer tools and protocols; research and training; retrieval
and memory; evaluation and reliability; infrastructure and inference; chips and
datacenters; image and video; voice and music; robotics and world models; science
and health; products and enterprise; business and policy; safety and security;
community and open source. Public community posts are attributed reports, with
original announcements and papers preferred for technical claims.

Each section gets a query. Source selection distributes the retained-source budget
across sections before taking extra results from the same section. The example
bounds one-provider acquisition to 17 searches, 48 retained sources and 12 original
page attempts. Coverage records distinguish search, retained evidence and published
stories. Quiet sections remain visible; story counts do not force filler.

```sh
python3 plugins/knowledge/skills/newsletter/scripts/newsletter.py refresh
python3 plugins/knowledge/skills/newsletter/scripts/newsletter.py collect --config /absolute/config.json
python3 plugins/knowledge/skills/newsletter/scripts/newsletter.py draft
python3 plugins/knowledge/skills/newsletter/scripts/newsletter.py review
python3 plugins/knowledge/skills/newsletter/scripts/newsletter.py validate
python3 plugins/knowledge/skills/newsletter/scripts/newsletter.py publish
```

By default the selected day's work lives in `ROOT/.work/YYYY-MM-DD`. `--work`
selects an explicit frozen work directory. The producer can also be composed
without the coordinator:

```sh
python3 plugins/knowledge/skills/newsletter/scripts/research.py \
  --config /absolute/config.json --work /absolute/work > research.json
python3 plugins/knowledge/skills/newsletter/scripts/draft.py draft --work /absolute/work
```

Artifacts are `research.json` (`newsletter-research/v1`), `issue.json`, and
`editorial-review.json` (`newsletter-review/v1`). A review contains `approved`,
`problems`, an assessment, and SHA-256 hashes of canonical JSON for the exact
issue/research objects (`json.dumps(..., ensure_ascii=False, sort_keys=True)`).
Every story cites a source ID and a short exact quote. The deterministic gate
checks coverage, minimum depth, quotes and revision binding; the separate model
review assesses support. Neither check proves factual correctness. Treat generated
applications as hypotheses and inspect material claims before acting on them.

The local publisher atomically installs `issues/YYYY-MM-DD` and regenerates
`index.html` and `latest.md`. Each edition includes both `issue.md` and `issue.html`,
the source record, editorial review and a hash-bound manifest. The reader works
from disk, with a centered publication layout, a linked quick briefing of up to six items,
search, topic filters, themes and an archive menu. Current stories follow editorial
importance; earlier and unconfirmed-date reading appears separately. Briefs contain
a summary of at most 100 words and essential caveats. Deep dives keep their full
technical analysis. HTML and Markdown number sources once per URL, in reading
order, and group exact supporting passages in a source disclosure.
Its coverage table includes every
searched section, including sections with no published story. Source text is escaped; no source HTML, external scripts,
images or frames execute in the reader.
If today's owned edition is already complete, the default daily run reuses it
without paid acquisition or model calls. Explicit work directories retain their
own frozen inputs and still require matching configuration and review.

## Schedule

Select an isolated Dagu home rather than modifying unrelated schedules. The
optional `scripts/host.py` reads an owner-only environment JSON file and starts
the scheduler with those variables. It never prints values. Local configuration
and credentials remain separate from the portable skill and published editions.

```sh
dagu validate plugins/knowledge/skills/newsletter/workflows/daily-newsletter.yaml
dagu start --run-id first-newsletter \
  plugins/knowledge/skills/newsletter/workflows/daily-newsletter.yaml -- \
  ROOT='/absolute/newsletters' CONFIG='/absolute/config.json'
```

For scheduled use, place the DAG in the selected scheduler's DAG directory with
an absolute `working_dir` pointing to this skill and the chosen ROOT/CONFIG
defaults. Enable Dagu queues in its isolated config for catch-up. Run
`dagu scheduler --dagu-home /absolute/dagu-home --dags /absolute/dags` under your
user's service supervisor. On macOS a user LaunchAgent runs while that user is
logged in; it cannot make a sleeping or powered-off Mac generate an edition.
`host.py` also exports `DAGU_HOME` and `DAGU_DAGS_DIR` so queued child runs use
the same isolated state as their scheduler.
Set `env_passthrough` in that isolated Dagu configuration to `PATH`,
`EXA_API_KEY` and `PARALLEL_API_KEY` so step processes receive provider variables.
Do not place key values in DAG parameters, YAML or step commands.

For `host.py`, use a local JSON object containing `EXA_API_KEY`, optional
`PARALLEL_API_KEY`, and `PATH`. Create it from inherited environment variables
with an owner-only mode (0600); keep values out of shell arguments and logs.
The supervisor invokes Python and `host.py` by absolute path. Shell startup files
are not a credential source for a LaunchAgent. Updating this file takes effect
when the scheduler restarts.

### Doppler

Fetch a selected secret at collection time by composing the independent CLIs:

```sh
doppler run --project PROJECT --config CONFIG \
  --only-secrets PARALLEL_API_KEY --no-fallback --preserve-env=false -- \
  python3 scripts/newsletter.py collect --config /absolute/newsletter.json
```

Use this command for the local DAG's `collect` step, from the newsletter skill
directory. Select the project/config explicitly and use an absolute Doppler path
in a service. `--only-secrets` limits secret injection; Doppler overrides a stale
inherited value, and `--no-fallback` requires a live fetch without a fallback file.
The search helper still reads its process environment. No provider key belongs in
the DAG or command arguments. The supervisor's user must have working Doppler
authentication; verify a scheduled child process, not only an interactive shell.
With this wrapper, Parallel does not need an `env_passthrough` entry: Doppler
injects its key inside the collection step rather than into the coordinator.

After a successful native Parallel preflight, select `exa,parallel` in the helper
command and both providers in the acquisition configuration. The 17-section sweep
then makes 34 search calls under the same retained-source and page-attempt bounds.

## Failure recovery and retention

Search responses, exact HTML inputs and extraction records are retained. Completed
stages reuse hash-bound outputs. `dagu retry --run-id RUN_ID PATH_TO_DAG` resumes
the same day's run. Use explicit `--work` commands for a run crossing midnight.
The DAG also accepts `WORK='/absolute/frozen-work'` for recovery across dates.
An interrupted model invocation leaves a `.pending.json` marker: inspect its logs
and candidate output before explicitly moving the marker aside to authorize another
attempt. There is no automatic paid/model retry. A failed editorial review holds
publication; correct it in a fresh work directory and obtain a matching new review.

If publication stops after installing the edition but before updating the reader,
retry the same unchanged publication or run `refresh`. Different content for an
existing date is refused. The existing issue is not overwritten.

Cleanup defaults to dry run. The scheduled workflow explicitly applies it:

```sh
python3 plugins/knowledge/skills/newsletter/scripts/newsletter.py cleanup
python3 plugins/knowledge/skills/newsletter/scripts/newsletter.py cleanup --apply
```

The threshold is strictly older than seven elapsed days in UTC, using manifest
publication/creation times, not file mtimes. Only this store's owned editions and
daily work directories are eligible. Ownership, hashes, inventory and symlinks
are checked before removal. A journal stages deletions under private names;
interrupted cleanup resumes on the next `cleanup --apply`. Unmanaged files,
configuration, credentials, bookmarks and insight libraries are outside retention.
The reader is rebuilt without removed editions, including an empty state if all
editions expire. Cleanup also runs before acquisition, so provider failures do
not indefinitely retain old newsletters.

The example caps acquisition and source sizes; each normal run invokes the drafting
model once and the reviewer once, with 15-minute deadlines. A timeout may still
incur provider charges. These local limits are not an account-wide billing cap.
Keep detailed quality comparisons and run evidence in the project wiki/archive.
