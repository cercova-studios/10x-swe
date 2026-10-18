#!/usr/bin/env python3
"""Bounded public web search; inherit provider keys from the environment.

Use --raw to retain provider-native evidence, warnings and usage.
Advanced research APIs are described in ../references/.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

DEFAULT_MODE = {"perplexity": "fast", "exa": "auto", "parallel": "fast"}
MODES = {"perplexity": {"fast", "standard"},
         "exa": {"instant", "fast", "auto", "deep-lite", "deep", "deep-reasoning"},
         "parallel": {"turbo", "fast", "basic", "advanced"}}
KEY = {"perplexity": "PERPLEXITY_API_KEY", "exa": "EXA_API_KEY", "parallel": "PARALLEL_API_KEY"}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # API credentials must never follow a redirect to another destination.
        return None


def post(url, body, headers):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "websearch/2", **headers})
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=90) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        # Response bodies can reflect credentials or sensitive input.
        error.close()
        raise RuntimeError(f"HTTP {error.code}; inspect provider status and request configuration") from None
    except (urllib.error.URLError, TimeoutError):
        raise RuntimeError("Network request failed or timed out; no automatic retry") from None
    except (ValueError, UnicodeError):
        raise RuntimeError("Provider returned invalid JSON") from None


def perplexity(q, mode, n, domains, fresh, key):
    body = {"query": q, "max_results": n}
    if mode == "fast":
        body["search_type"] = "fast"
    if domains:
        body["search_domain_filter"] = domains
    return post("https://api.perplexity.ai/search", body, {"Authorization": f"Bearer {key}"})


def exa(q, mode, n, domains, fresh, key):
    contents = {"highlights": True}
    if fresh:
        contents["maxAgeHours"] = 0
    body = {"query": q, "type": mode, "numResults": n, "contents": contents}
    if domains:
        body["includeDomains"] = domains
    return post("https://api.exa.ai/search", body, {"x-api-key": key})


def parallel(q, mode, n, domains, fresh, key):
    advanced = {"max_results": n}
    if domains:
        advanced["source_policy"] = {"include_domains": domains}
    if fresh:
        advanced["fetch_policy"] = {"max_age_seconds": 600, "disable_cache_fallback": True}
    body = {"objective": q, "search_queries": [q], "mode": mode, "advanced_settings": advanced}
    return post("https://api.parallel.ai/v1/search", body, {"x-api-key": key})


FN = {"perplexity": perplexity, "exa": exa, "parallel": parallel}


def compact(provider, response, limit):
    field = {"perplexity": "snippet", "exa": "highlights", "parallel": "excerpts"}[provider]
    results = []
    for row in response.get("results", [])[:limit]:
        excerpt = row.get(field) or ""
        if isinstance(excerpt, list):
            excerpt = "\n".join(excerpt)
        results.append(dict(title=row.get("title"), url=row["url"], excerpt=excerpt))
    return results


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("query")
    ap.add_argument("-p", "--providers", default="perplexity", help="comma-separated: perplexity,exa,parallel")
    ap.add_argument("-m", "--mode", help="mode override for one selected provider; see provider reference")
    ap.add_argument("-n", type=int, default=5, help="results per provider, 1–20 (default 5)")
    ap.add_argument("-d", "--domain", action="append", help="hard domain allowlist; repeatable")
    ap.add_argument("--fresh", action="store_true", help="Exa live crawl; Parallel <=600s with stale fallback disabled")
    ap.add_argument("--chars", type=int, default=700, help="positive human-display excerpt limit (default 700)")
    output = ap.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true", help="compact JSON results")
    output.add_argument("--raw", action="store_true", help="JSON envelope with complete native responses")
    a = ap.parse_args(argv)
    providers = [p.strip() for p in a.providers.split(",")]
    if not a.query.strip() or not 1 <= a.n <= 20 or a.chars <= 0:
        ap.error("query must be nonempty, -n must be 1–20, and --chars must be positive")
    if any(p not in FN for p in providers) or len(set(providers)) != len(providers):
        ap.error("select distinct, nonempty providers from perplexity,exa,parallel")
    if a.mode and (len(providers) != 1 or a.mode not in MODES[providers[0]]):
        ap.error("--mode must be a supported mode for exactly one provider")
    if a.fresh and "perplexity" in providers:
        ap.error("--fresh is supported only for Exa and Parallel")
    if a.domain and any(not domain.strip() for domain in a.domain):
        ap.error("--domain must be nonempty")
    missing = [KEY[p] for p in providers if not os.environ.get(KEY[p])]
    if missing:
        ap.error("missing environment variables: " + ", ".join(missing))

    def run(provider):
        try:
            response = FN[provider](a.query, a.mode or DEFAULT_MODE[provider], a.n,
                                    a.domain, a.fresh, os.environ[KEY[provider]])
            results = compact(provider, response, a.n)
            return provider, response, results, None
        except RuntimeError as error:
            return provider, None, [], str(error)
        except Exception:
            return provider, None, [], "Invalid provider response; no automatic retry"

    with ThreadPoolExecutor(len(providers)) as executor:
        out = list(executor.map(run, providers))
    if a.json or a.raw:
        print(json.dumps({p: {"error": error, **({"response": response} if a.raw else {"results": results})}
                          for p, response, results, error in out}, ensure_ascii=False, indent=1))
    else:
        for provider, response, results, error in out:
            print(f"## {provider} ({a.mode or DEFAULT_MODE[provider]}{', fresh requested' if a.fresh else ''})")
            if error:
                print(f"ERROR: {error}")
            for index, row in enumerate(results, 1):
                excerpt = " ".join(row["excerpt"].split())
                print(f"[{index}] {row['title'] or '(no title)'}\n    {row['url']}\n    "
                      f"{excerpt[:a.chars]}{'…' if len(excerpt) > a.chars else ''}")
            if response and (response.get("warnings") or response.get("statuses")):
                print("Provider warnings/statuses present; inspect --raw before relying on the result.")
            print()
    return 2 if any(error for _, _, _, error in out) else 0


if __name__ == "__main__":
    sys.exit(main())
