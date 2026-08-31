"""The upnext command line: import, enrich, inspect, serve."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from upnext.catalog.enrich import enrich
from upnext.catalog.tmdb import TMDBClient, TMDBError
from upnext.importers.tvtime import ExportError, read_export
from upnext.models import Status
from upnext.settings import load_settings
from upnext.store.db import open_library
from upnext.store.library import Library


def cmd_import(args: argparse.Namespace) -> int:
    settings = load_settings()
    try:
        imported = read_export(args.export_dir)
    except ExportError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    with open_library(args.db or settings.db_path) as conn:
        count = Library(conn).ingest(imported)
    watches = sum(len(item.watches) for item in imported)
    by_status = {status: sum(1 for i in imported if i.state.status is status) for status in Status}

    print(f"Imported {count} titles and {watches} watches into {args.db or settings.db_path}")
    for status, n in by_status.items():
        if n:
            print(f"  {status.value:<10} {n}")
    print("\nNext: `upnext enrich` to resolve these against TMDB.")
    return 0


def cmd_enrich(args: argparse.Namespace) -> int:
    settings = load_settings()
    with open_library(args.db or settings.db_path) as conn:
        library = Library(conn)
        pending = library.needing_enrichment(limit=args.limit)
        if not pending:
            print("Nothing to enrich — every title already has catalog data.")
            return 0

        try:
            client = TMDBClient(
                settings.tmdb_api_key,
                language=settings.tmdb_language,
                min_interval_seconds=settings.tmdb_min_interval_seconds,
            )
        except TMDBError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

        def progress(title, ok: bool) -> None:
            print(f"  {'✓' if ok else '·'} {title.name}", flush=True)

        print(f"Enriching {len(pending)} titles from TMDB…")
        result = enrich(client, library, pending, on_progress=progress)
    print(f"\nMatched {len(result.matched)} of {result.total}.")
    if result.unmatched:
        print("Not found on TMDB (left as imported):")
        for name in result.unmatched:
            print(f"  - {name}")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    settings = load_settings()
    with open_library(args.db or settings.db_path) as conn:
        stats = Library(conn).stats()
    print(f"{stats['episodes_watched']} episodes across {stats['titles_watched']} titles")
    if stats["first_watch"]:
        print(f"from {stats['first_watch'][:10]} to {stats['last_watch'][:10]}")
    hours = stats["known_minutes"] // 60
    if hours:
        print(f"at least {hours:,} hours of known runtime")
    for status, n in stats["by_status"].items():
        print(f"  {status:<10} {n}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    settings = load_settings()
    uvicorn.run("upnext.web.api:app", host=args.host or settings.host, port=args.port or settings.port)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="upnext", description="A personal TV and film watch tracker.")
    parser.add_argument("--db", type=Path, help="Library path (default: ~/.upnext/library.db)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_import = sub.add_parser("import", help="Ingest a TV Time export folder")
    p_import.add_argument("export_dir", type=Path)
    p_import.set_defaults(func=cmd_import)

    p_enrich = sub.add_parser("enrich", help="Resolve imported titles against TMDB")
    p_enrich.add_argument("--limit", type=int, default=None, help="Only enrich the first N titles")
    p_enrich.set_defaults(func=cmd_enrich)

    p_stats = sub.add_parser("stats", help="Summarise the library")
    p_stats.set_defaults(func=cmd_stats)

    p_serve = sub.add_parser("serve", help="Serve the API")
    p_serve.add_argument("--host")
    p_serve.add_argument("--port", type=int)
    p_serve.set_defaults(func=cmd_serve)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
