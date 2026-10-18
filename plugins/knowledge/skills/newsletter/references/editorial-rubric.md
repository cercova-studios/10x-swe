# Editorial rubric

Use these criteria for copywriting and independent review. Apply them to the
headline, standfirst, editorial and every story, including visible limitations.
Judge the supplied evidence, not whether a claim sounds plausible.

Use `coverage`, `evidence_kind` and `provenance` to identify what was actually
read. A curated case-study summary or AIETalks write-up supports attributed
summary claims; an original-source link does not prove that source was read.
Automated transcript passages support only the retained words and timestamps,
not uninspected slides or the full recording. Multiple catalogs describing the
same recording are one source, not independent corroboration. Keep unknown
publication dates unknown; catalog addition times and reported years do not
establish a publication date. Attribution must appear beside secondary claims.

| Criterion | Accept | Block |
|---|---|---|
| Support | Each material clause follows from a cited passage. | An exact quotation is attached to a broader, unsupported claim. |
| Measurement | Preserve the workload, baseline, hardware, precision and attribution needed to interpret a result. | Merge results from different setups or present a vendor result as independent validation. |
| Freshness | Use the source publication date; keep unknown or earlier events as context. | Treat retrieval time, index addition time or republication as a new event. |
| Inference | Attribute observations and label proposed applications as hypotheses. | Infer causation, general availability or universal performance from a narrow observation. |
| Reader value | State a concrete development and its useful implication concisely. | Repeat an event, inflate novelty or add material only to fill a topic quota. |

Synthetic boundary examples illustrate the criteria; they are not news evidence:

- Source: a vendor reports 12% higher throughput on one GPU in a synthetic test.
  Accept: the vendor reports that result under those conditions. Block: the model
  makes production deployments 12% faster. Reason: the production claim exceeds
  the workload and measures a different outcome.
- Source: task success moves from 40% to 50% in the same evaluation.
  Accept: a rise of 10 percentage points, or 25% relative. Block: a rise of 10%.
  Reason: relative change and percentage-point change differ.
- Source: adoption and latency change during the same period, without a causal
  study. Accept: both observations, attributed separately. Block: adoption caused
  the latency change. Reason: co-occurrence does not establish causation.

For each rejection, identify the criterion, story ID or top-level field, offending
clause, relevant source ID and a short evidence-based explanation. Distinguish
missing evidence from evidence that contradicts the claim. State the smallest
necessary correction; do not invent replacement facts. A supported synonym or
stylistic preference alone is not a blocker. Approval requires no material blocker.
