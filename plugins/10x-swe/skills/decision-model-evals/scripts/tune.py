"""Threshold tuning and calibration check for saved decision-model scores.

Input JSON: [{"model": str, "id": str, "score": float, "label": 0|1}, ...]
Run with --self-check to verify the logic on synthetic data.
"""
import argparse
import json
import sys
from collections import defaultdict

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, fbeta_score, precision_score, recall_score
from sklearn.model_selection import StratifiedKFold


def metrics(y, s, t, beta):
    p = (s >= t).astype(int)
    return (precision_score(y, p, zero_division=0), recall_score(y, p, zero_division=0),
            fbeta_score(y, p, beta=beta, zero_division=0))


def pick_threshold(y, s, beta, min_p, min_r):
    """Best F-beta threshold meeting both floors; None if no threshold qualifies."""
    best = None
    for t in np.unique(s):
        p, r, f = metrics(y, s, t, beta)
        if p >= min_p and r >= min_r and (best is None or f > best[1]):
            best = (t, f)
    return None if best is None else best[0]


def logit(s):
    s = np.clip(s, 1e-6, 1 - 1e-6)
    return np.log(s / (1 - s)).reshape(-1, 1)


def evaluate(y, s, args):
    skf = StratifiedKFold(args.folds, shuffle=True, random_state=args.seed)
    rows, infeasible, platt = [], 0, np.zeros_like(s)
    for tr, va in skf.split(s, y):
        t = pick_threshold(y[tr], s[tr], args.beta, args.min_precision, args.min_recall)
        if t is None:  # report, never relax the floors
            infeasible += 1
            continue
        rows.append(metrics(y[va], s[va], t, args.beta) + (t,))
        lr = LogisticRegression().fit(logit(s[tr]), y[tr])
        platt[va] = lr.predict_proba(logit(s[va]))[:, 1]
    out = {"default_0.50": dict(zip(("precision", "recall", "fbeta"), metrics(y, s, 0.5, args.beta))),
           "infeasible_folds": f"{infeasible}/{args.folds}",
           "brier_raw": brier_score_loss(y, s)}
    if rows:
        m = np.array(rows)
        out["tuned_cv"] = {k: f"{m[:, i].mean():.3f} ± {m[:, i].std():.3f}"
                           for i, k in enumerate(("precision", "recall", "fbeta", "threshold"))}
    if infeasible == 0:  # Platt preds cover every trace only when all folds ran
        out["brier_platt"] = brier_score_loss(y, platt)
    return out


def self_check():
    rng = np.random.default_rng(0)
    y = np.array([1] * 60 + [0] * 40)
    s = np.where(y == 1, rng.uniform(0.3, 0.5, 100), rng.uniform(0.0, 0.2, 100))
    a = argparse.Namespace(folds=5, seed=0, beta=1.0, min_precision=0.8, min_recall=0.8)
    r = evaluate(y, s, a)
    assert r["default_0.50"]["recall"] == 0.0, r          # default misses everything
    assert float(r["tuned_cv"]["fbeta"].split()[0]) > 0.95, r  # tuned ~separates; CV gap allowed
    assert r["infeasible_folds"] == "0/5"
    a.min_precision = 1.01                                # impossible floor
    assert evaluate(y, s, a)["infeasible_folds"] == "5/5"
    print("self-check ok")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scores", nargs="?")
    ap.add_argument("--min-precision", type=float, default=0.0)
    ap.add_argument("--min-recall", type=float, default=0.0)
    ap.add_argument("--beta", type=float, default=1.0)
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--self-check", action="store_true")
    args = ap.parse_args()
    if args.self_check:
        return self_check()
    if not args.scores:
        ap.error("scores file required")
    by_model = defaultdict(lambda: ([], []))
    for r in json.load(open(args.scores)):
        by_model[r["model"]][0].append(r["label"])
        by_model[r["model"]][1].append(r["score"])
    report = {m: evaluate(np.array(y), np.array(s, float), args) for m, (y, s) in by_model.items()}
    json.dump(report, sys.stdout, indent=2, default=float)
    print()


if __name__ == "__main__":
    main()
