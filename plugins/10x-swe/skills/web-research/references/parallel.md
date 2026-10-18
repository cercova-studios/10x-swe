# Parallel research routes

Use the [documentation index](https://docs.parallel.ai/llms.txt) and
[OpenAPI schema](https://docs.parallel.ai/public-openapi.json) to verify the chosen
endpoint. API base: `https://api.parallel.ai`; key: `PARALLEL_API_KEY`.
The `parallel-cli` is an optional independent client. Inspect its installed help;
CLI defaults and exposed features can differ from the HTTP API.

## Search, extraction and images

[GA Search](https://docs.parallel.ai/search/search-quickstart), `POST /v1/search`,
requires `search_queries`. Provide one atomic `objective` with two or three concise,
related query variations. Use separate calls for independent questions.
[Modes](https://docs.parallel.ai/search/modes): `fast` for interactive retrieval,
`turbo` for the lowest-cost/latency workload, `basic` for longer excerpts, `advanced`
for more complex retrieval. These are use-case choices, not measured quality guarantees.
Set the mode deliberately: HTTP defaults to advanced; CLI defaults may differ.

[Advanced Search settings](https://docs.parallel.ai/search/advanced-search-settings)
belong inside `advanced_settings`:

- `source_policy`: include/exclude domains or path prefixes, and `after_date`.
  Includes are hard corpus restrictions; say “prefer official sources” in the
  objective when a preference is sufficient. Turbo does not support path prefixes.
- `fetch_policy`: `max_age_seconds` (minimum 600), `timeout_seconds` and
  `disable_cache_fallback`. Freshness requests can fall back to older indexed content;
  set `disable_cache_fallback: true` when that fallback would invalidate the result.
- `excerpt_settings.max_chars_per_result`, `max_results` and `location`.
  Check current limits and warnings. Top-level `max_chars_total` bounds total excerpts.
  These are output/context controls, not spend caps or proof of complete recall.

Minimal GA request:

```json
{
  "objective": "Find official guidance for PostgreSQL hybrid retrieval",
  "search_queries": ["PostgreSQL hybrid retrieval documentation", "PostgreSQL vector keyword search"],
  "mode": "fast",
  "advanced_settings": {"max_results": 5}
}
```

[Extract](https://docs.parallel.ai/extract/advanced-extract-settings),
`POST /v1/extract`, takes related `urls` and an optional extraction objective.
Use excerpts first; request bounded full content when a reader or downstream
summarizer needs it. **GA `full_content`, `fetch_policy` and `excerpt_settings`
belong inside `advanced_settings`**; old beta top-level fields can return 422.
Full content can truncate from the beginning rather than prioritize the objective.
Check requested URLs against successes, errors, timestamps and truncation.
Extract has no documented cache-only security guarantee; enforce egress restrictions
outside the API when required. A connector's cached-content flag is not a network sandbox.

[Image Search](https://docs.parallel.ai/image-search/image-search-quickstart),
`POST /v1/images/search`, finds images separately from text Search. Preserve source
page/image URLs and inspect relevance and usage rights before reuse.

With an installed, configured CLI, these commands return JSON suitable for pipes:

```sh
parallel-cli search 'Find official PostgreSQL hybrid retrieval guidance' \
  -q 'PostgreSQL hybrid retrieval documentation' -q 'PostgreSQL vector keyword search' \
  --mode fast --max-results 5 --json
parallel-cli extract https://docs.parallel.ai/search/modes \
  --objective 'Explain the tradeoffs between search modes' --json
```

## Answers, research and enrichment

| Capability | Use and evidence |
|---|---|
| [Responses](https://docs.parallel.ai/responses-api/responses-quickstart) | `POST /v1/responses` provides sourced answers, structured outputs, streaming and multi-turn context via `previous_response_id`. Preserve citation annotations and available search/page-read traces. Check supported OpenAI-compatible fields instead of assuming parity. |
| [Task](https://docs.parallel.ai/task-api/task-quickstart) | `/v1/tasks/runs` executes a repeatable task spec with input/output schemas and a selected processor. Choose a processor from current docs/help based on difficulty and latency; don't escalate tiers automatically. Preserve `output.content` and field/item-level `basis` citations, reasoning and confidence. |
| [Task Ingest](https://docs.parallel.ai/task-api/ingest-api) | `/v1beta/tasks/suggest` and `/v1beta/tasks/suggest-processor` help draft schemas and processor choices. Inspect suggestions and budget before execution; suggestions do not authorize a run. |
| [Task Groups](https://docs.parallel.ai/task-api/group-api) | Group independent runs, add bounded batches, track statuses/events and retrieve each result. Use explicit row identities; retry only failed rows. Enrichment CLI and DuckDB/Polars/Spark/warehouse integrations serve supplied datasets; they are not entity discovery. |
| [Interactions](https://docs.parallel.ai/task-api/guides/interactions) | Reuse prior Task context deliberately; save interaction IDs and distinguish them from run IDs. Recheck evidence age before reusing conclusions. |
| [Data connectors](https://docs.parallel.ai/task-api/data-connectors) | Tasks/Responses can use selected licensed sources and remote MCP tools. Establish source permissions, retention and incremental charges. Review remote tools' effects and credentials; enabling a tool is an authority change. |

For authorized long research, the CLI supports a reviewable dry run and later recovery:

```sh
printf '%s\n' 'Compare PostgreSQL retrieval options using primary sources' |
  parallel-cli research run - --processor core --text --dry-run
```

After approval of scope and spend, omit `--dry-run` and use `--no-wait` to capture
the run ID; recover with `parallel-cli research poll RUN_ID --json`. A polling
timeout leaves the remote task running. Check status and reuse that ID after failure;
do not blindly resubmit an ambiguous create. Persist outputs before transformation.
Use bounded polling/backoff, SSE or verified webhooks according to the API family.

## Entity discovery, monitors and saved research

- [Entity Search](https://docs.parallel.ai/findall-api/entity-search),
  `/v1beta/findall/entity-search`, synchronously returns a people/company shortlist.
  Its limited fields do not provide FindAll's per-condition evaluation or citations.
- [FindAll](https://docs.parallel.ai/findall-api/findall-quickstart),
  `/v1beta/findall/runs`, discovers entities against match conditions. Use Ingest to
  draft a spec and preview to test it before scale. Inspect candidate match states,
  condition evidence and enrichments; separate matches from uncertain/rejected
  candidates. Deduplicate identities, retain exclusions, retrieve current results and use
  extend/refresh/cancel deliberately. Match limits are not proof of exhaustiveness.
  Do not replace these documented beta paths with guessed `/v1` paths.
- [Monitors](https://docs.parallel.ai/monitor-api/monitor-quickstart), `/v1/monitors`,
  support pulse discovery and [snapshot comparison](https://docs.parallel.ai/monitor-api/quickstart-snapshot)
  against a completed Task baseline. Specify schedule, recipients and retention.
  Retrieve events and verify webhook signatures/replay handling. Optional follow-up
  Tasks create more work and cost; authorize those separately. Trigger/update/cancel
  are account mutations; cancellation can be irreversible. New integrations use GA
  paths rather than the old monitor alpha API.
- [Memory](https://docs.parallel.ai/resources/memory) explicitly retrieves previous
  Task, Monitor and FindAll work. Personal memory availability/settings vary; outputs
  may be retained when enabled. Application memory uses an explicit `memory_scope_key`.
  Inspect provenance and age before reuse. Clear/evict changes retained state and
  must not be a cleanup side effect of research.

Capture request/run IDs, input/schema revision, processor/mode, warnings, partial
failures, usage and timestamps. Treat provider confidence as a judgment, not a
calibrated probability. Inspect the cited passages before relying on material claims.
Do not confuse a completed job with every row succeeding or every claim being supported.

Account OAuth, keys, prepaid balance, payments, deployments and organization settings
are administrative capabilities. They are discoverable in the documentation index;
research does not implicitly authorize changing them or funding an account.
