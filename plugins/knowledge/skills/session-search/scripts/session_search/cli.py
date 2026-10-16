from __future__ import annotations

import argparse
import json
import sys
import sqlite3
from datetime import datetime, timezone

from . import adapters
from .models import Hit, SearchResult, StrategyUnavailable
from .store import Store, default_db_path
from .strategies import run as run_strategy
from .textutil import parse_since, snippet
from .turns import excerpts
from .records import export_snapshot

COMMANDS = {"index", "search", "last", "show", "status", "export"}


def main(argv: list[str] | None = None) -> int:
    argv = _normalize_argv(list(sys.argv[1:] if argv is None else argv))
    if not argv:
        _parser().print_help()
        return 2
    args = _parser().parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, RuntimeError, OSError, sqlite3.Error) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2


def _normalize_argv(argv: list[str]) -> list[str]:
    if not argv:
        return argv
    if argv[0] in {"-h", "--help"}:
        return argv
    cmd_idx = next((i for i, a in enumerate(argv) if a in COMMANDS), None)
    if cmd_idx is not None:
        return [argv[cmd_idx], *argv[:cmd_idx], *argv[cmd_idx + 1 :]]
    if argv[0] not in COMMANDS:
        return ["search", *argv]
    return argv


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="session-search",
        description="Search local public conversation text with bounded provenance-preserving exports.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_index = sub.add_parser("index", help="crawl adapters into the local FTS index")
    p_index.add_argument("--agent", choices=adapters.agent_choices())
    p_index.add_argument("--enrich-only", action="store_true", help="rebuild embeddings and insights from the existing session index")
    p_index.add_argument("--json", action="store_true")
    p_index.set_defaults(func=cmd_index)

    p_search = sub.add_parser("search", help="search the index")
    _add_search_flags(p_search)
    p_search.set_defaults(func=cmd_search, last=False)

    p_export = sub.add_parser("export", help="emit one bounded knowledge-snapshot/v1 JSONL record")
    _add_search_flags(p_export)
    p_export.add_argument('--role',choices=['user','assistant','tool'],help='Filter exported excerpts by public turn role; session ranking is unchanged')
    p_export.set_defaults(func=cmd_search, last=False, export=True)

    p_last = sub.add_parser("last", help="most recent matching session")
    _add_search_flags(p_last, with_limit=False)
    p_last.set_defaults(func=cmd_search, last=True, limit=1)

    p_show = sub.add_parser("show", help="print one indexed session")
    p_show.add_argument("agent")
    p_show.add_argument("session_id")
    p_show.add_argument("--json", action="store_true")
    p_show.set_defaults(func=cmd_show)

    p_status = sub.add_parser("status", help="index stats")
    p_status.add_argument("--json", action="store_true")
    p_status.set_defaults(func=cmd_status)
    return p


def _add_search_flags(p: argparse.ArgumentParser, *, with_limit: bool = True) -> None:
    p.add_argument("query", nargs="+")
    p.add_argument("--mode", choices=["auto", "naive", "semantic", "onto"], default="auto")
    p.add_argument("--agent", choices=adapters.agent_choices())
    p.add_argument("--since", help="e.g. 14d, 24h, or ISO timestamp")
    p.add_argument("--json", action="store_true")
    if with_limit:
        p.add_argument("--limit", type=int, default=10)


def cmd_index(args: argparse.Namespace) -> int:
    store = Store()
    if getattr(args, "enrich_only", False):
        records = store.all_records(agent=args.agent)
        stats = store.enrich(records, agent=args.agent)
        payload = {"db": str(store.path), "enrich": stats, "sessions": len(records)}
        if args.json:
            json.dump(payload, sys.stdout, indent=2)
            sys.stdout.write("\n")
        else:
            print(f"enriched {len(records)} sessions  embeddings={stats['embeddings']} insights={stats['insights']}")
        return 0
    counts: dict[str, int] = {}
    errors: dict[str, str] = {}
    for name, records, err in adapters.crawl(args.agent):
        if err:
            errors[name] = err
            counts[name] = 0
            continue
        counts[name] = store.replace_agent(name, records)
        for old in adapters.SUPERSEDED.get(name, []):
            store.replace_agent(old, [])
    if not errors:
        store.set_meta("indexed_at", datetime.now(tz=timezone.utc).isoformat())
    payload = {"db": str(store.path), "counts": counts, "errors": errors, "total": sum(counts.values())}
    if args.json:
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        for name, n in counts.items():
            extra = f"  error: {errors[name]}" if name in errors else ""
            print(f"{name:10} {n}{extra}")
        if errors and not counts:
            return 1
        print(f"{'total':10} {payload['total']}")
    return 1 if errors else 0


def cmd_search(args: argparse.Namespace) -> int:
    query = " ".join(args.query).strip()
    if not query:
        print("empty query", file=sys.stderr)
        return 2
    if not 1 <= int(getattr(args, 'limit', 10)) <= 20 or len(query.encode()) > 400:
        raise ValueError('Query must be at most 400 bytes and limit 1–20')
    store = Store()
    if store.count() == 0:
        raise ValueError("Index empty; run session-search index explicitly")
    last = bool(getattr(args, "last", False))
    limit = 1 if last else int(getattr(args, "limit", 10))
    try:
        result = run_strategy(
            store,
            query,
            mode=args.mode,
            last=last,
            limit=limit,
            agent=args.agent,
            since_ms=parse_since(args.since),
        )
    except StrategyUnavailable as exc:
        if args.json and not getattr(args, 'export', False):
            json.dump({"error": exc.reason, "mode": exc.name}, sys.stdout)
            sys.stdout.write("\n")
        else:
            print(f"{exc.name}: {exc.reason}", file=sys.stderr)
        return 2
    for hit in result.hits:
        rec = store.get(hit.agent, hit.native_id)
        hit.citations = excerpts(rec, query)
    if getattr(args, 'export', False):
        if not result.hits:
            print('No sessions found; no record exported', file=sys.stderr)
            return 1
        print(json.dumps(export_snapshot(store, result, role=getattr(args,'role',None)), ensure_ascii=False, separators=(',', ':')))
        return 0
    if args.json:
        json.dump(result.as_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        _print_result(result, last=last)
    return 0 if result.hits else 1


def cmd_show(args: argparse.Namespace) -> int:
    store = Store()
    rec = store.get(args.agent, args.session_id)
    if rec is None:
        print("not found", file=sys.stderr)
        return 1
    if args.json:
        json.dump(
            {
                "id": rec.id,
                "agent": rec.agent,
                "native_id": rec.native_id,
                "cwd": rec.cwd,
                "title": rec.title,
                "summary": rec.summary,
                "snippet": snippet(rec.body or rec.summary or rec.title),
                "updated_at": rec.updated_at,
                "source_path": rec.source_path,
            },
            sys.stdout,
            indent=2,
        )
        sys.stdout.write("\n")
        return 0
    print(f"agent:    {rec.agent}")
    print(f"session:  {rec.native_id}")
    print(f"when:     {_fmt_time(rec.updated_at)}")
    print(f"cwd:      {rec.cwd}")
    print(f"title:    {rec.title}")
    print(f"source:   {rec.source_path}")
    print()
    print(snippet(rec.summary or rec.body or rec.title, n=800))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    path = default_db_path()
    payload = {
        "db": str(path),
        "exists": path.exists(),
        "indexed_at": None,
        "embedder": None,
        "total": 0,
        "embeddings": 0,
        "insights": 0,
        "counts": {},
    }
    if path.exists():
        store = Store(path)
        payload["indexed_at"] = store.get_meta("indexed_at")
        payload["embedder"] = store.get_meta("embedder")
        payload["total"] = store.count()
        payload["embeddings"] = store.embedding_count()
        payload["insights"] = store.insight_count()
        payload["counts"] = store.counts_by_agent()
    if args.json:
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0
    print(f"db:         {payload['db']}")
    print(f"indexed_at: {payload['indexed_at'] or '(never)'}")
    print(f"embedder:   {payload['embedder'] or '(none)'}")
    print(f"total:      {payload['total']}")
    print(f"embeddings: {payload['embeddings']}")
    print(f"insights:   {payload['insights']}")
    for agent, n in payload["counts"].items():
        print(f"  {agent:10} {n}")
    return 0


def _print_result(result: SearchResult, *, last: bool) -> None:
    skipped = ", ".join(f"{k} ({v})" for k, v in result.strategies_skipped.items())
    used = ",".join(result.strategies_used) or result.mode
    print(f"mode={result.mode} used={used}" + (f" skipped={skipped}" if skipped else ""))
    if not result.hits:
        print("no hits")
        return
    for hit in result.hits:
        _print_hit(hit, last=last)


def _print_hit(hit: Hit, *, last: bool) -> None:
    when = _fmt_time(hit.updated_at)
    if last:
        print(f"agent:    {hit.agent}")
        print(f"session:  {hit.native_id}")
        print(f"when:     {when}")
        print(f"cwd:      {hit.cwd}")
        print(f"title:    {hit.title}")
        print(f"strategy: {hit.strategy}")
        print(f"snippet:  {hit.snippet}")
        return
    print()
    print(f"{hit.agent:10} {when}  {hit.cwd}")
    print(f"  {hit.title}")
    if hit.snippet:
        print(f"  {hit.snippet}")


def _fmt_time(ms: int) -> str:
    if not ms:
        return "?"
    dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc).astimezone()
    return dt.strftime("%Y-%m-%d %H:%M")


if __name__ == "__main__":
    raise SystemExit(main())
