---
name: decision-model-evals
description: 'Choose, tune, and trust any model that returns a probability for a yes/no
  decision: decision-model APIs (Jev, Perplexity Decider, Liquid d1, Cloudflare Clef,
  OpenAI Decisions), LLM judges that emit scores, or classic classifiers. Use when
  picking a decision threshold, comparing decision models on cost vs. quality, setting
  precision/recall floors, or deciding whether a score can be read as a confidence.
  Do NOT use for error analysis or writing the criterion (error-discovery, write-judge-prompt),
  or for judges that only return Pass/Fail with no score (validate-evaluator).

  '
---

# Decision Model Evals

A decision model returns a score in [0, 1] for a yes/no question. The API turns
it into a decision at a default threshold, usually 0.50. That default is
arbitrary for your data: a model that scores every failure 0.40 and every pass
0.10 is perfect at 0.30 and catches nothing at 0.50. Everything below is
standard classifier evaluation applied to these models.

Primary source: Husain & Saha, "How To Use Decision Models for Evals"
(https://hamel.dev/blog/posts/decision-model-evals/, 2026-10-20).

## Prerequisites

- A fixed criterion and prompt, one failure mode per judge (write-judge-prompt).
- Human binary labels on representative traces (1 = the positive class, e.g.
  failure). Labels are the oracle; bad labels poison every step below.
- Saved scores per (model, trace). Score once, tune offline. Threshold tuning
  and calibration never need new model calls.
- A held-out test set that no tuning step touches.

## Workflow

1. **Set floors from the use case before looking at results.** Write down the
   minimum precision and recall at which the classifier is useful (e.g. alerting:
   both ≥ 0.80). Rule out models whose PR curve never enters that region.
2. **Pick the objective deliberately.** F1 weights precision and recall equally,
   which is rarely true. Use F-beta (beta < 1 favors precision, > 1 favors
   recall), or expected cost when you can price a false positive and a false
   negative: threshold* ≈ C_fp / (C_fp + C_fn) for a calibrated model.
3. **Tune the threshold per model with cross-validation.** Stratified k-fold,
   same splits for every model. Choose the threshold on training folds only,
   among thresholds that meet the floors; if none qualifies, record that split
   as infeasible. Do not relax the floors to get a number. Report validation
   precision, recall, objective, infeasible-split count, and the 0.50 baseline.
4. **Compare on the cost/quality Pareto frontier.** Plot tuned objective vs.
   cost per N calls. Discard dominated models. Consider latency separately; it
   depends on batching, region, and contract, so measure it in your deployment.
5. **Check calibration only if you use the score as a confidence** (routing,
   escalation bands, aggregation across judges). Reliability diagram plus Brier
   score, out-of-fold. Try Platt scaling on log-odds (clip away from 0/1);
   isotonic only with plenty of data. Keep the mapping only if Brier improves;
   calibration can make an already-good model worse.
6. **Iterate.** A prompt change invalidates the threshold and calibration. Re-run
   steps 3–5. Prefer a larger model first, then test whether cheaper ones match.

`scripts/tune.py` does steps 3 and 5 from a JSON file of saved scores.

```bash
uv run --with numpy --with scikit-learn \
  scripts/tune.py scores.json \
  --min-precision 0.8 --min-recall 0.8 --beta 1
```

Input: `[{"model": "...", "id": "...", "score": 0.73, "label": 1}, ...]`.

## Pitfalls

| Pitfall | Why it hurts | Do instead |
|---|---|---|
| Shipping the 0.50 default | Leaves recall or precision on the table | Tune per model, per criterion |
| Reporting the best test-set threshold | Oracle upper bound, not deployable | Choose on train folds, report on held-out |
| Maximizing F1 by habit | Encodes "FP cost = FN cost" silently | F-beta or explicit costs |
| Comparing untuned models | Ranks defaults, not models | Tune each, then compare |
| Reading 0.8 as "80% likely" | Raw scores are often miscalibrated | Reliability diagram first |
| Tuning on a balanced set, deploying on skewed traffic | Precision collapses at low prevalence | Tune at production prevalence, or reweight |
| Tiny sample, confident claims | ~100 traces gives wide intervals | Report fold spread; label more |
| Leaking test data into prompt tuning | Optimistic final numbers | Keep a test set outside all tuning |

## Cascade

Cheap decision model first; route its uncertain band (e.g. 0.3–0.7, chosen by
CV) to a critique-producing LLM judge or a human. This only works if the band
means something, so calibrate first (step 5). See jev-evaluators for a worked
version.

## Related skills

- llm-evaluation: broader evaluation strategy and metrics.
- If installed: write-judge-prompt (criterion), validate-evaluator (Pass/Fail
  judges without scores), jev-evaluators (Jev-specific API).
