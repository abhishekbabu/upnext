"""The upnext command line: import, enrich, inspect, serve.

An inbound adapter, so this is where a raised `UpnextError` stops being an
exception and becomes an exit code and a line on stderr — in `main`, once.
"""

from __future__ import annotations

import argparse
import threading
from collections.abc import Callable, Sequence
from pathlib import Path

from pydantic import ValidationError

from upnext import bootstrap
from upnext.adapters.inbound.cli import output
from upnext.adapters.outbound.store.library import Library, open_library
from upnext.application.enrichment import enrich, move_season, relink
from upnext.application.importing import import_export
from upnext.config.settings import DEFAULT_DB_PATH, Settings
from upnext.domain.errors import NotFoundError, UpnextError

EXIT_OK = 0
EXIT_FAILED = 2


def cmd_import(args: argparse.Namespace, settings: Settings, library: Library) -> None:
    summary = import_export(bootstrap.IMPORT_SOURCES[args.source], library, args.export_dir)
    output.imported(summary, settings.db_path)


def cmd_enrich(args: argparse.Namespace, settings: Settings, library: Library) -> None:
    # Enrichment is a snapshot: a show enriched in August knows nothing of a
    # season TMDB added in October. A refresh asks again for every title, most
    # recently watched first.
    pending = library.titles()[: args.limit] if args.refresh else library.needing_enrichment(limit=args.limit)
    if not pending:
        output.nothing_to_enrich(library_is_empty=library.count_titles() == 0)
        return
    catalog = bootstrap.build_catalog(settings)
    output.enriching(len(pending))
    output.enrichment_done(enrich(catalog, library, pending, on_progress=output.enriched_one))


def cmd_move(args: argparse.Namespace, settings: Settings, library: Library) -> None:
    source = library.title(args.title)
    if source is None:
        raise NotFoundError(
            f"No title with id {args.title}. GET /api/titles lists them; it is in a title page's URL too."
        )
    result = move_season(
        bootstrap.build_catalog(settings),
        library,
        source=source,
        tmdb_id=args.to,
        season=args.season,
        as_season=args.season if args.as_season is None else args.as_season,
    )
    output.moved(source.name, args.season, result)


def cmd_relink(args: argparse.Namespace, settings: Settings, library: Library) -> None:
    linked = relink(library, library.titles())
    # Read again: relinking changed the counts. Before enrichment every viewing
    # is unmatched because nothing has been asked, which is not a disagreement
    # with TMDB and is not listed as one.
    output.relinked(linked, [row for row in library.titles() if row.enriched_at and row.unmatched_watched])


def cmd_stats(args: argparse.Namespace, settings: Settings, library: Library) -> None:
    output.stats(library.stats())


type Command = Callable[[argparse.Namespace, Settings], None]


def in_library(command: Callable[[argparse.Namespace, Settings, Library], None]) -> Command:
    def run(args: argparse.Namespace, settings: Settings) -> None:
        with open_library(settings.db_path) as library:
            command(args, settings, library)

    return run


def serve(args: argparse.Namespace, settings: Settings) -> None:
    import uvicorn

    from upnext.adapters.inbound.web.api import app, get_settings

    app.dependency_overrides[get_settings] = lambda: settings
    if not args.no_refresh:
        refresh_in_background(settings)
    uvicorn.run(app, host=args.host or settings.host, port=args.port or settings.port)


def refresh_in_background(settings: Settings) -> threading.Thread | None:
    """Fetch every title from TMDB again, beside the server rather than before it.

    The timeline is only as current as the last fetch, and a server start is
    when someone is about to look at it. In a thread, so the page loads at once
    and fills in as titles land: enrichment commits per title, and the thread
    has its own connection. Skipped without a key — browsing never needed one.
    """
    if not settings.tmdb_api_key:
        output.refresh_skipped()
        return None

    def refresh() -> None:
        try:
            catalog = bootstrap.build_catalog(settings)
            with open_library(settings.db_path) as library:
                titles = library.titles()
                output.refreshing(len(titles))
                output.refreshed(enrich(catalog, library, titles))
        except UpnextError as exc:
            output.error(f"Refresh stopped: {exc}")

    thread = threading.Thread(target=refresh, name="refresh", daemon=True)
    thread.start()
    return thread


def _row_id(value: str) -> int:
    # SQLite integers are 64-bit; a larger one is an OverflowError, not a miss.
    number = int(value)
    if not 0 < number < 2**63:
        raise argparse.ArgumentTypeError(f"not a library id: {value}")
    return number


def _positive(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError(f"must be 1 or more, not {value}")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="upnext", description="A personal TV and film watch tracker.")
    parser.add_argument("--db", type=Path, help=f"Library path (default: {DEFAULT_DB_PATH})")
    sub = parser.add_subparsers(dest="command", required=True)

    p_import = sub.add_parser("import", help="Ingest an export folder")
    p_import.add_argument("export_dir", type=Path)
    p_import.add_argument(
        "--source",
        default=bootstrap.DEFAULT_IMPORT_SOURCE,
        choices=sorted(bootstrap.IMPORT_SOURCES),
        help="Which service the export came from",
    )
    p_import.set_defaults(func=in_library(cmd_import))

    p_enrich = sub.add_parser("enrich", help="Resolve imported titles against TMDB")
    p_enrich.add_argument("--limit", type=_positive, default=None, help="Only enrich the first N titles")
    p_enrich.add_argument(
        "--refresh", action="store_true", help="Fetch titles already enriched again too, for new seasons and episodes"
    )
    p_enrich.set_defaults(func=in_library(cmd_enrich))

    p_move = sub.add_parser(
        "move",
        help="Move a season's watches to the TMDB title they actually belong to",
        description=(
            "For where the export and TMDB disagree about what counts as one show — "
            "TV Time files The Haunting of Bly Manor as season 2 of The Haunting, and "
            "TMDB keeps it as its own title."
        ),
    )
    p_move.add_argument(
        "--title", type=_row_id, required=True, help="The library id of the title to move a season out of"
    )
    p_move.add_argument("--season", type=int, required=True, help="The season, as the export numbered it")
    p_move.add_argument("--to", type=int, required=True, metavar="TMDB_ID", help="The TMDB id to move it to")
    p_move.add_argument(
        "--as-season",
        type=int,
        default=None,
        help="Which season it is at the target (default: unchanged)",
    )
    p_move.set_defaults(func=in_library(cmd_move))

    p_relink = sub.add_parser("relink", help="Re-match recorded watches against stored episodes")
    p_relink.set_defaults(func=in_library(cmd_relink))

    p_stats = sub.add_parser("stats", help="Summarise the library")
    p_stats.set_defaults(func=in_library(cmd_stats))

    p_serve = sub.add_parser("serve", help="Serve the API")
    p_serve.add_argument("--host")
    p_serve.add_argument("--port", type=int)
    p_serve.add_argument("--no-refresh", action="store_true", help="Skip fetching every title from TMDB on start")
    p_serve.set_defaults(func=serve)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = Settings()
    except ValidationError as exc:
        output.error("; ".join(f"UPNEXT_{str(e['loc'][0]).upper()}: {e['msg']}" for e in exc.errors()))
        return EXIT_FAILED
    if args.db is not None:
        settings = settings.model_copy(update={"db_path": args.db})
    try:
        args.func(args, settings)
    except UpnextError as exc:
        output.error(str(exc))
        return EXIT_FAILED
    return EXIT_OK
