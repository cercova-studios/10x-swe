#!/usr/bin/env python3
"""Frozen synthetic relevance cases, evaluated through the actual CLI."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess
import tempfile
import time


def run(binary, home, args):
    started = time.perf_counter()
    p = subprocess.run([str(binary), "--home", str(home), *args], capture_output=True,
                       text=True, timeout=120)
    return p, time.perf_counter() - started


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--semantic", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--split", choices=["development", "held-out", "all"], default="all")
    args = parser.parse_args()
    binary = args.binary.resolve()
    fixture = Path(__file__).parent / "fixtures/retrieval.json"
    raw = fixture.read_bytes()
    corpus = json.loads(raw)
    cases = [c for c in corpus["queries"] if args.split == "all" or c["split"] == args.split]
    results = []
    with tempfile.TemporaryDirectory(prefix="bkd-benchmark-") as temp:
        home = Path(temp) / "state"
        records = Path(temp) / "records.jsonl"
        records.write_text("".join(json.dumps(r) + "\n" for r in corpus["records"]))
        index_args = ["index", str(records), "--json"]
        if not args.semantic:
            index_args.append("--lexical-only")
        indexed, index_seconds = run(binary, home, index_args)
        assert indexed.returncode == 0, indexed.stderr or indexed.stdout
        for case in cases:
            query_args = ["search", case["query"], "--json", "--limit", "10"]
            if not args.semantic:
                query_args.append("--lexical-only")
            query_args += case.get("flags", [])
            response, seconds = run(binary, home, query_args)
            assert response.returncode == 0, response.stderr or response.stdout
            hits = json.loads(response.stdout)["data"]["results"]
            urls = [h["url"] for h in hits]
            labels = case["relevance"]
            relevant = {u for u, grade in labels.items() if grade > 0}
            gain = lambda grade: 2**grade - 1
            dcg = sum(gain(labels.get(u, 0)) / math.log2(i + 2) for i, u in enumerate(urls))
            ideal = sum(gain(g) / math.log2(i + 2)
                        for i, g in enumerate(sorted(labels.values(), reverse=True)[:10]))
            top_one = (not urls if not relevant else bool(urls) and labels.get(urls[0], 0) == max(labels.values()))
            recall = len(relevant.intersection(urls)) / len(relevant) if relevant else float(not urls)
            violated = bool(set(urls).intersection(case.get("forbidden", [])))
            # Default stdout must be exactly the same top URL, without model chatter.
            plain_args = [a for a in query_args if a != "--json"]
            plain, plain_seconds = run(binary, home, plain_args)
            if urls:
                assert plain.returncode == 0 and plain.stdout == urls[0] + "\n", plain.stderr
            else:
                assert plain.returncode != 0 and not plain.stdout, plain.stderr
            results.append({"id": case["id"], "split": case["split"], "top_one": top_one,
                            "recall_at_10": recall, "ndcg_at_10": dcg / ideal if ideal else float(not urls),
                            "constraint_violation": violated, "seconds": seconds,
                            "plain_seconds": plain_seconds, "urls": urls})
    timings = sorted(r["plain_seconds"] for r in results)
    report = {"schema": 1, "fixture_sha256": hashlib.sha256(raw).hexdigest(),
              "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
              "semantic": args.semantic, "index_seconds": index_seconds,
              "queries": len(results), "top_one_accuracy": statistics.mean(r["top_one"] for r in results),
              "mean_recall_at_10": statistics.mean(r["recall_at_10"] for r in results),
              "mean_ndcg_at_10": statistics.mean(r["ndcg_at_10"] for r in results),
              "constraint_violations": sum(r["constraint_violation"] for r in results),
              "plain_p50_seconds": statistics.median(timings),
              "plain_p95_seconds": timings[math.ceil(len(timings) * .95) - 1], "cases": results,
              "limitations": ["Synthetic corpus and author-specified labels; no statistical generalization.",
                              "Held-out cases are regression checks, not a blinded independent evaluation.",
                              "Latency includes process startup and warm OS caches on this machine."]}
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "cases"}, indent=2))
    if args.check:
        assert report["constraint_violations"] == 0
        failures = [r["id"] for r in results if not r["top_one"]]
        assert not failures, f"Incorrect first result: {failures}"


if __name__ == "__main__":
    main()
