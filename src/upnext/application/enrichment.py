"""Resolve imported titles against a catalog and fill in the real data.

Both collaborators are ports and both are supplied. Nothing here knows that the
catalog is TMDB or that the library is SQLite; `bootstrap` does the wiring.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from upnext.domain.errors import CatalogError
from upnext.domain.models import Status, TitleRow, TitleState
from upnext.domain.ports import Catalog, CatalogShow, WatchLibrary


@dataclass(slots=True)
class EnrichmentResult:
    matched: list[str] = field(default_factory=list)
    unmatched: list[str] = field(default_factory=list)
    """Titles the catalog has never heard of, left exactly as imported."""

    failed: list[tuple[str, str]] = field(default_factory=list)
    """Titles the catalog knew but could not serve, with why. Nothing was
    stamped, so the next `enrich` tries them again."""

    @property
    def total(self) -> int:
        return len(self.matched) + len(self.unmatched) + len(self.failed)


def resolve_show(catalog: Catalog, title: TitleRow) -> int | None:
    """The catalog's id for an imported show, or None if it has none.

    The TheTVDB id is tried first because it is an identity rather than a
    guess. Name search is the fallback for shows the catalog has never mapped,
    and it is kept strict — the first result only, and only when the year
    agrees if the import knew one — because a wrong match here corrupts the
    library far more visibly than a missing one. A candidate whose year the
    catalog does not know is not a disagreement, so it is allowed through.
    """
    if title.tmdb_id:
        return title.tmdb_id
    if title.tvdb_id and (found := catalog.find_by_tvdb(title.tvdb_id)):
        return found.catalog_id

    for candidate in catalog.search_shows(title.name, year=title.year)[:1]:
        if title.year and candidate.year is not None and candidate.year != title.year:
            continue
        return candidate.catalog_id
    return None


def _store_show(library: WatchLibrary, title_id: int, show: CatalogShow) -> None:
    library.apply_enrichment(title_id, show.title, enriched_at=datetime.now(UTC).isoformat(timespec="seconds"))
    for episode in show.episodes:
        library.upsert_episode(title_id, episode)


def enrich_title(catalog: Catalog, library: WatchLibrary, title: TitleRow) -> bool:
    """Enrich one show in place. Returns whether the catalog knew it.

    Committed per title: enrichment walks every season of every show in one
    run, and a failure at show 140 must not discard the 139 already resolved.
    Matching runs on every enrichment, because a catalog that adds an episode
    should pick up the viewings that were waiting for it.
    """
    catalog_id = resolve_show(catalog, title)
    if catalog_id is None:
        return False

    _store_show(library, title.id, catalog.fetch_show(catalog_id))
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

    A catalog failure on one title does not end the run: the title keeps
    exactly what the import gave it and is picked up again by the next
    `enrich`, because nothing stamped it as enriched. A `ConfigurationError`
    does end it — no other title will fare better.
    """
    result = EnrichmentResult()
    for title in titles:
        try:
            ok = enrich_title(catalog, library, title)
        except CatalogError as exc:
            result.failed.append((title.name, str(exc)))
            ok = False
        else:
            (result.matched if ok else result.unmatched).append(title.name)
        if on_progress is not None:
            on_progress(title, ok)
    return result


def relink(library: WatchLibrary, titles: Iterable[TitleRow]) -> int:
    """Match recorded viewings against the episode lists already stored.

    Enrichment does this per title as it goes, but only for titles it enriches
    — so a library sitting on a full episode list never benefits from an
    improvement to how matching works. This is that improvement applied, with
    no network and no catalog: everything it needs is already in the library.
    """
    linked = sum(library.link_watches(title.id) for title in titles)
    library.commit()
    return linked


@dataclass(slots=True)
class MoveResult:
    """What moving a season did."""

    target: str
    moved: int
    linked: int


def move_season(
    catalog: Catalog,
    library: WatchLibrary,
    *,
    source: TitleRow,
    tmdb_id: int,
    season: int,
    as_season: int,
) -> MoveResult:
    """Move one source season's viewings to the catalog title they belong to.

    The export and the catalog disagree about what counts as one show more
    often than they disagree about episodes: a spin-off filed as season 2 of its
    parent, or a revival filed as later seasons of the original, where TMDB
    keeps each as its own title. The viewings are right; the show they were
    filed under is not.

    Deliberately something a person asks for. Finding the right title needs
    knowledge upnext does not have — TMDB has no "this is season 2 of that"
    relation, so anything automatic here would be a name search and a hope,
    which is exactly the kind of invention the rest of this module refuses.

    The target is created and enriched if the library does not have it, the
    viewings are re-numbered into the target's own seasons, and matching runs
    again from scratch.

    Raises:
        CatalogError: the catalog could not serve the target title.
    """
    show = catalog.fetch_show(tmdb_id)

    existing = library.title_by_tmdb_id(tmdb_id)
    if existing is None:
        target_id = library.upsert_title(show.title)
        # The state is a guess and there is only one worth making: whatever the
        # user's relationship to the show they filed it under was.
        library.set_state(target_id, TitleState(status=source.status or Status.WATCHING))
    else:
        target_id = existing.id
    _store_show(library, target_id, show)

    moved = library.move_watches(source_id=source.id, target_id=target_id, season=season, as_season=as_season)
    linked = library.link_watches(target_id)
    # The source keeps whatever it still has, and its counts have to be redone
    # now that a season has left it.
    library.link_watches(source.id)
    library.commit()

    return MoveResult(target=show.title.name, moved=moved, linked=linked)
