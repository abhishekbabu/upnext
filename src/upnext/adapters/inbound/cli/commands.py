"""The upnext command line: import, enrich, inspect, serve.

An inbound adapter, so this is where a raised `UpnextError` stops being an
exception and becomes an exit code and a line on stderr.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from upnext import bootstrap
from upnext.adapters.inbound.cli import output
from upnext.adapters.outbound.store.db import open_library
from upnext.adapters.outbound.store.library import Library
from upnext.application.enrichment import enrich, relink
from upnext.application.importing import import_export
from upnext.config.settings import load_settings
from upnext.domain.errors import UpnextError

APP_PATH = "upnext.adapters.inbound.web.api:app"

EXIT_OK = 0
EXIT_FAILED = 2


def cmd_import(args: argparse.Namespace) -> int:
    settings = load_settings()
    db_path = args.db or settings.db_path
    try:
        source = bootstrap.import_source(args.source)
        with open_library(db_path) as conn:
            summary = import_export(source, Library(conn), args.export_dir)
    except UpnextError as exc:
        output.error(str(exc))
        return EXIT_FAILED

    output.imported(summary, db_path)
    return EXIT_OK


def cmd_enrich(args: argparse.Namespace) -> int:
    settings = load_settings()
    with open_library(args.db or settings.db_path) as conn:
        library = Library(conn)
        pending = library.needing_enrichment(limit=args.limit)
        if not pending:
            output.nothing_to_enrich(library_is_empty=library.count_titles() == 0)
            return EXIT_OK

        try:
            catalog = bootstrap.build_catalog(settings)
        except UpnextError as exc:
            output.error(str(exc))
            return EXIT_FAILED

        output.enriching(len(pending))
        result = enrich(catalog, library, pending, on_progress=output.enriched_one)

    output.enrichment_done(result)
    return EXIT_OK


def cmd_relink(args: argparse.Namespace) -> int:
    settings = load_settings()
    with open_library(args.db or settings.db_path) as conn:
        library = Library(conn)
        linked = relink(library, library.titles())
        unmatched = [row for row in library.titles() if row.unmatched_watched]
    output.relinked(linked, unmatched)
    return EXIT_OK


def cmd_stats(args: argparse.Namespace) -> int:
    settings = load_settings()
    with open_library(args.db or settings.db_path) as conn:
        summary = Library(conn).stats()
    output.stats(summary)
    return EXIT_OK


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    settings = load_settings()
    uvicorn.run(APP_PATH, host=args.host or settings.host, port=args.port or settings.port)
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="upnext", description="A personal TV and film watch tracker.")
    parser.add_argument("--db", type=Path, help="Library path (default: ~/.upnext/library.db)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_import = sub.add_parser("import", help="Ingest an export folder")
    p_import.add_argument("export_dir", type=Path)
    p_import.add_argument(
        "--source",
        default=bootstrap.DEFAULT_IMPORT_SOURCE,
        choices=sorted(bootstrap.IMPORT_SOURCES),
        help="Which service the export came from",
    )
    p_import.set_defaults(func=cmd_import)

    p_enrich = sub.add_parser("enrich", help="Resolve imported titles against TMDB")
    p_enrich.add_argument("--limit", type=int, default=None, help="Only enrich the first N titles")
    p_enrich.set_defaults(func=cmd_enrich)

    p_relink = sub.add_parser("relink", help="Re-match recorded watches against stored episodes")
    p_relink.set_defaults(func=cmd_relink)

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
