"""Resolve imported titles against a catalog and fill in the real data.

Both collaborators are ports and both are supplied. Nothing here knows that the
catalog is TMDB or that the library is SQLite; `bootstrap` does the wiring.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from upnext.domain.errors import CatalogError
from upnext.domain.models import TitleRow
from upnext.domain.ports import Catalog, CatalogMatch, WatchLibrary


@dataclass(slots=True)
class EnrichmentResult:
    matched: list[str]
    unmatched: list[str]

    @property
    def total(self) -> int:
        return len(self.matched) + len(self.unmatched)


def resolve_show(catalog: Catalog, title: TitleRow) -> CatalogMatch | None:
    """Find the catalog's show for an imported one.

    The TheTVDB id is tried first because it is an identity rather than a
    guess. Name search is the fallback for shows the catalog has never mapped,
    and it is kept strict — the first result only, and only when the year
    agrees if the import knew one — because a wrong match here corrupts the
    library far more visibly than a missing one. A candidate whose year the
    catalog does not know is not a disagreement, so it is allowed through.
    """
    if title.tmdb_id:
        return CatalogMatch(catalog_id=title.tmdb_id, name=title.name, year=title.year)
    if title.tvdb_id:
        found = catalog.find_by_tvdb(title.tvdb_id)
        if found:
            return found

    for candidate in catalog.search_shows(title.name, year=title.year)[:1]:
        if title.year and candidate.year is not None and candidate.year != title.year:
            continue
        return candidate
    return None


def enrich_title(catalog: Catalog, library: WatchLibrary, title: TitleRow) -> bool:
    """Enrich one show in place. Returns whether the catalog knew it.

    Committed per title: enrichment walks every season of every show in one
    run, and a failure at show 140 must not discard the 139 already resolved.
    """
    match = resolve_show(catalog, title)
    if match is None:
        return False

    show = catalog.fetch_show(match.catalog_id)
    library.apply_enrichment(
        title.id,
        show.title,
        enriched_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )
    for episode in show.episodes:
        library.upsert_episode(title.id, episode)

    # The episode list is the catalog's; the history was recorded in whatever
    # the exporting service called things. This is where the two meet, and it
    # runs on every enrichment because a catalog that adds an episode should
    # pick up the viewings that were waiting for it.
    library.link_watches(title.id)

    library.commit()
    return True


def enrich(
    catalog: Catalog,
    library: WatchLibrary,
    titles: Iterable[TitleRow],
    *,
    on_progress: Callable[[TitleRow, bool], None] | None = None,
) -> EnrichmentResult:
    """Enrich every title given, reporting each as it lands.

    A catalog failure on one title counts as unmatched rather than ending the
    run: the title keeps exactly what the import gave it and is picked up again
    by the next `enrich`, because nothing stamped it as enriched.
    """
    result = EnrichmentResult(matched=[], unmatched=[])
    for title in titles:
        try:
            ok = enrich_title(catalog, library, title)
        except CatalogError:
            ok = False
        (result.matched if ok else result.unmatched).append(title.name)
        if on_progress is not None:
            on_progress(title, ok)
    return result
