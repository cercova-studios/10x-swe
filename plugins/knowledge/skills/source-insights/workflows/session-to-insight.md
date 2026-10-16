---
schema: workflow/v1
name: session-to-insight
description: Capture selected session evidence, review exact citations and destination, and publish reusable insights locally with Dagu.
skills:
  - global/session-search
  - global/source-insights
runner: workflows/session-to-insight.yaml
resources:
  - workflows/session-to-insight.yaml
  - scripts/session_workflow.py
---

# Session to insight

Dagu 2.19.2 coordinates existing CLIs. This document is discovery metadata, not
authorization. The YAML and recipe are owned by source-insights; neither producer
nor publisher depends on Dagu. Skill-search only indexes documents and hashes
their resources. Graph relationships never execute a workflow.

Inputs: an inspected complete session packet, exact `session:codex:ID` or
`session:claude:ID`, matching agent, fresh absolute work directory and explicit
destination library. Export once and retain the selected packet before Dagu runs:

```sh
session-search export --mode naive --agent codex --role assistant --limit 1 'topic' > selected.jsonl.tmp && mv selected.jsonl.tmp selected.jsonl
```

Inspect the selected ID, excerpt roles and coverage. `--role assistant` omits tool
logs explicitly; use user for requirements or tool for observed outcomes. Omit the
flag for all roles. A session claim is not independent corroboration. Run
`session-search status` first; if recent work is missing, explicitly refresh with
`session-search index --agent codex`. Dagu never indexes the session store itself.
Only Codex and Claude currently provide exact exported turn provenance.

Outputs: `records.jsonl`, line-cited `evidence/`, human-authored `analysis.json`,
`publication.json` and `insights.jsonl`. Effects: local work/log files and, only
after approval, immutable entries and a derived index in the chosen library.
No Neon, public website, cloud AI, skill mutation or automatic analysis.

## Run

Use a Python 3.10+ installation on PATH and the installed `session-search` CLI.
The local Dagu config explicitly passes PATH and SESSION_SEARCH_DB; it binds the
optional UI to loopback, disables update checks and has no cloud reporting.
CLI runs work without a server. To resume human tasks automatically, start the optional local UI and scheduler:

```sh
dagu start-all --dags "$HOME/.agents/skills/source-insights/workflows"
```

Keep that foreground process running in another terminal. The coordinator is disabled; start-all also disables the standalone scheduler’s wildcard health listener. Then choose paths and
run (replace SESSION with the ID you inspected):

```sh
dagu start --run-id my-session-learning \
  "$HOME/.agents/skills/source-insights/workflows/session-to-insight.yaml" -- \
  RECORDS='/absolute/selected.jsonl' SESSION='session:codex:EXACT_ID' AGENT=codex \
  WORK='/absolute/fresh/work' LIBRARY='/absolute/chosen/library'
```

The workflow freezes the supplied packet without rerunning search, then pipes it to
`sources.py prepare-session --records -`, and persists a native waiting human task.
Read WORK/evidence/document.md and the coverage omissions. Write WORK/analysis.json
using the [analysis contract](../references/analysis-format.md). Quotes must be
exact and cite the retained document's line numbers; recalled claims remain leads.
Review with the same session and destination:

```sh
python3 "$HOME/.agents/skills/source-insights/scripts/session_workflow.py" review \
  --work '/absolute/fresh/work' --session 'session:codex:EXACT_ID' \
  --library '/absolute/chosen/library'
dagu human-task complete session-to-insight --run-id my-session-learning \
  --step review --input decision=publish --input digest=REVIEW_DIGEST
```

Submit the printed digest only after inspecting evidence, claims, citations and
destination. It pins all six artifacts, the runner/recipe bytes, session ID and
canonical library path. Changed bytes or destination invalidate approval. The
publisher gets a verified snapshot and independently checks citations. `reject`
denies publication and yields a visible failed publish step. It is not silent success. To reject without authoring analysis, submit decision=reject and a 64-zero digest.
Local completion is an operator decision, not authenticated proof of human review;
another process under the same Unix account can submit it. Agents must not submit
publication approval without explicit user authorization.

## Compose

Successful output remains a portable packet. For example:

```sh
cat '/absolute/fresh/work/insights.jsonl' | bkd --records - search 'topic'
skill-search export --query 'session learning' > skills.jsonl
```

The recipe also accepts stdin without Dagu:

```sh
python3 "$HOME/.agents/skills/source-insights/scripts/session_workflow.py" capture \
  --records - --session 'session:codex:EXACT_ID' --work '/absolute/fresh/work' \
  --library '/absolute/chosen/library' < selected.jsonl
```

Use QUERY instead of RECORDS if Dagu should perform the initial search; it still
requires an explicit selected ID and rejects another session. Do not specify both
unless the query matches the packet. Failed producers can emit valid partial data,
so retain successful output before handing it to a consumer; a pipe alone cannot
prove the producer exited successfully.

Only concatenate successful completed packets. Record consumers never invoke
companion tools, import their libraries or read private indexes. The workflow can
be replaced by explicit CLI composition without changing producer contracts.

## Recover

```sh
dagu status session-to-insight --run-id my-session-learning
dagu retry --run-id my-session-learning \
  "$HOME/.agents/skills/source-insights/workflows/session-to-insight.yaml"
```

Failed capture leaves no published packet. Retry freezes an existing successful
capture instead of searching again. Preparation verifies and reuses exact evidence.
Pending approval remains pending on retry. Without start-all, complete the human task and explicitly run retry to resume. A changed analysis needs a new review
digest; after completing a native gate, use a fresh run/work directory to review
changed content. Retrying an unchanged approved publication deduplicates the entry.
If export fails after publication, `publication.json` records the confirmed entry;
retry restores the export without creating another entry. A post-publication index
error reports the retained entry; diagnose it before retry. Never delete published
entries as workflow cleanup. Dagu logs and work directories remain for diagnosis.

The optional UI and scheduler are `dagu start-all --dags "$HOME/.agents/skills/source-insights/workflows"`
at `http://127.0.0.1:8099`. Stop foreground processes with Ctrl-C. No login item,
recurring schedule or resident service is installed.

References: [Dagu human tasks](https://docs.dagu.sh/writing-workflows/human-tasks),
[Dagu source/release](https://github.com/dagucloud/dagu/releases/tag/v2.19.2).
