# Exa research routes

Use the [documentation index](https://exa.ai/docs/llms.txt) to find the current
product page. Check the [OpenAPI schema](https://exa.ai/docs/exa-spec.yaml) for
HTTP fields and the installed SDK reference for language-specific names.
The API base is `https://api.exa.ai`; credentials use `EXA_API_KEY`.

## Search and read

- [Search](https://exa.ai/docs/search/quickstart): `POST /search` takes a rich
  description of the ideal page in `query`, plus an optional task `objective`.
  Select `auto`, `fast`, `instant`, `deep-lite`, `deep` or `deep-reasoning` explicitly
  when the tradeoff matters. Request `contents.highlights` before full text.
- Restrict the corpus with `includeDomains`/`excludeDomains` only when required;
  domain/path restrictions can reduce recall. Use published-date bounds for publication
  time and `userLocation` only when location matters. Categories include `publication`,
  `news`, `personal site`, `financial report`, `company` and `people`. Category-specific
  filters have restrictions: inspect the current schema before combining them.
- [Deep Search](https://exa.ai/docs/search/deep-search) performs iterative retrieval.
  `additionalQueries` supplies up to ten starting variations for Deep types.
  `systemPrompt` guides source preferences and synthesis. `outputSchema` works across
  search types; retain `output.content` together with field-level `output.grounding`.
  Follow current schema size/depth limits instead of adding citation fields yourself.
- [Contents](https://exa.ai/docs/contents/quickstart): `POST /contents` accepts document
  `ids` or `urls` (choose one). Ask for query-focused highlights, bounded text, summaries,
  subpages or link extras as needed. Check every URL's status and available content.
  Summaries are generated; inspect extracted code, tables, figures and PDFs against
  the source when layout or exact fidelity matters. Use browser/PDF tools for visual evidence.
- Freshness: `maxAgeHours` controls content age; `0` requests live crawling.
  On Search it belongs inside `contents`; on Contents it is top-level. Inspect
  statuses and timestamps instead of equating a request with successful fresh extraction.
- [Snapshot](https://exa.ai/docs/search/snapshot): `snapshotAsOf` selects a stored
  version at or before a cutoff (inside Search `contents`, top-level for Contents).
  Missing snapshots can produce `CONTENT_NOT_CACHED`. Coverage and plan limits apply;
  this is not an exhaustive archive of the historical web. Use current fields instead
  of deprecated `livecrawl`, crawl-date or combined-context aliases.
  Omit live-fetch and subpage options entirely when using a snapshot. Search snapshot
  support depends on mode/account and excludes categories; inspect the compatibility
  section before combining controls. Historical content still uses current retrieval
  signals to rank candidate URLs.
- [Find Similar](https://exa.ai/docs/reference/find-similar-links): `POST /findSimilar`
  expands a known URL into related pages. Keep the seed and each discovered URL in
  provenance. [Answer](https://exa.ai/docs/reference/answer), `POST /answer`, supplies
  a cited synthesis; retain citations and verify consequential statements.

Minimal HTTP Search body, usable with an existing authorized API client:

```json
{
  "query": "Official documentation explaining hybrid retrieval in PostgreSQL",
  "type": "auto",
  "numResults": 5,
  "contents": {"highlights": true}
}
```

## Research, collections and scale

| Capability | Use and operating contract |
|---|---|
| [Agent](https://exa.ai/docs/agent/quickstart) | `POST /agent/runs` for longer research, list building and enrichment. Set `query`, `outputSchema` and deliberate `effort`. Preserve run ID, structured output, grounding, events and costs. Retrieve/list prior runs or continue with `previousRunId` when supported by the account's retention policy. |
| [Connect](https://exa.ai/docs/agent/connect/overview) | Agent `dataSources` adds selected premium partner databases: company/contact, traffic, business verification, financial/economic, market, catalog, podcast and travel sources. Check provider access, additive charges, permitted data and ZDR eligibility before attaching any source. |
| [Websets](https://exa.ai/docs/websets/quickstart) | `/v0/websets` creates a retained entity collection with search criteria and enrichments. Preview criteria before scale; inspect verification evidence, paginate items and export only reviewed matches. Imports, exclusions, enrichment runs, cancellation and Websets Monitors have separate effects. |
| [Batch](https://exa.ai/docs/batch/quickstart) | `/batches` runs independent Search or Agent items with stable `customId`s. This is access-gated; check current enablement and beta-header requirements. Persist the batch ID, poll/list, retrieve JSONL and inspect each item's response/error. A completed batch can contain failures. |
| [Search Monitors](https://exa.ai/docs/monitors/quickstart) | `/monitors` schedules a search, deduplicates new findings and keeps run history. Choose schedule, schema and webhook destination explicitly; trigger/update/delete are distinct operations. These are separate from `/v0/monitors` for Websets. |

For async work, save the created ID before waiting. Poll with a deadline and backoff
or consume events; reconnect to the same run after interruption. Agent `stop` requests
an early finish with available work; `cancel` abandons execution. Inspect terminal
status before consuming output. A local timeout does not cancel remote work. After an
ambiguous create failure, inspect recent runs before submitting again. Retry transient
reads/rate limits within a bound; never blindly duplicate creates or recurring schedules.

Keep raw costs, partial failures, pagination cursors and provider warnings. Download
presigned batch results without forwarding API credentials to their storage host.
Verify webhook signatures with the product's documented scheme, deduplicate deliveries
and retain a polling recovery route; do not expose a new receiver without authorization.

## Access, privacy and integrations

[Exa MCP](https://exa.ai/docs/get-started/exa-mcp) can expose more tools than an app
connector, including Agent. Inspect the actual enabled tool list before invocation.
[OpenAI compatibility](https://exa.ai/docs/integrations/openai-sdk) covers Answer/chat
and Agent via Responses, including streaming/background operation; use the documented
base URL, model and supported fields rather than assuming complete OpenAI API parity.

[ZDR](https://exa.ai/docs/admin/security/zero-data-retention) is an account/product
contract, not a setting inferred from an API key. Agent continuation and partner data
have restrictions under ZDR. Enterprise compliance modes, account/team management,
OAuth setup and billing are separate administrative operations; consult their current
documentation and authorization rather than adding them to a research loop.
