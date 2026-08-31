"""Everything the CLI prints.

Separated from the commands so that what a command *did* and how it reads are
different questions. This is one of the two modules allowed to write to a
stream; the other is the HTTP layer, which writes status codes.
"""

from __future__ import annotations

import sys
from pathlib import Path

from upnext.application.enrichment import EnrichmentResult
from upnext.application.importing import ImportSummary
from upnext.domain.models import TitleRow


def error(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)


def imported(summary: ImportSummary, db_path: Path) -> None:
    print(f"Imported {summary.titles} titles and {summary.watches} watches into {db_path}")
    for status, count in summary.by_status.items():
        print(f"  {status.value:<10} {count}")
    print("\nNext: `upnext enrich` to resolve these against TMDB.")


def nothing_to_enrich(library_is_empty: bool) -> None:
    """Say which kind of nothing this is.

    An empty library and a fully enriched one both have no pending titles, and
    reporting them the same way sends someone hunting for a broken API key when
    what they actually need is `upnext import`.
    """
    if library_is_empty:
        print("Nothing to enrich — the library is empty. Run `upnext import <export-dir>` first.")
    else:
        print("Nothing to enrich — every title already has catalog data.")


def enriching(count: int) -> None:
    print(f"Enriching {count} titles from TMDB…")


def enriched_one(title: TitleRow, ok: bool) -> None:
    print(f"  {'✓' if ok else '·'} {title.name}", flush=True)


def enrichment_done(result: EnrichmentResult) -> None:
    print(f"\nMatched {len(result.matched)} of {result.total}.")
    if result.unmatched:
        print("Not found on TMDB (left as imported):")
        for name in result.unmatched:
            print(f"  - {name}")


def relinked(linked: int, unmatched: list[TitleRow]) -> None:
    print(f"Matched {linked} more {'watch' if linked == 1 else 'watches'} to episodes.")
    if not unmatched:
        print("Every watch is accounted for by TMDB's episode lists.")
        return
    # Named rather than totalled: these are the titles where the export and
    # TMDB genuinely describe the show differently, and which they are is the
    # useful part.
    print("\nNot in TMDB's lists (kept, and shown on the title page):")
    for row in sorted(unmatched, key=lambda r: -r.unmatched_watched):
        print(f"  {row.name[:38]:<38} {row.episodes_watched}/{row.total_episodes or '?'}  +{row.unmatched_watched}")


def stats(summary: dict) -> None:
    print(f"{summary['episodes_watched']} episodes across {summary['titles_watched']} titles")
    if summary["first_watch"]:
        print(f"from {summary['first_watch'][:10]} to {summary['last_watch'][:10]}")
    hours = summary["known_minutes"] // 60
    if hours:
        print(f"at least {hours:,} hours of known runtime")
    for status, count in summary["by_status"].items():
        print(f"  {status:<10} {count}")
