"""Resolve imported titles against TMDB and fill in the real catalog data."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from upnext.catalog.tmdb import TMDBClient, TMDBError, episodes_from_season, title_from_show
from upnext.models import Kind
from upnext.store.library import Library, TitleRow


@dataclass(slots=True)
class EnrichmentResult:
    matched: list[str]
    unmatched: list[str]

    @property
    def total(self) -> int:
        return len(self.matched) + len(self.unmatched)


def resolve_show(client: TMDBClient, title: TitleRow) -> dict | None:
    """Find the TMDB show for an imported one.

    The TheTVDB id is tried first because it is an identity rather than a
    guess. Name search is the fallback for shows TMDB has never mapped, and it
    is kept strict — the first result only, and only when the year agrees if
    the import knew one — because a wrong match here corrupts the library far
    more visibly than a missing one.
    """
    if title.tmdb_id:
        return {"id": title.tmdb_id}
    if title.tvdb_id:
        found = client.find_by_tvdb(title.tvdb_id)
        if found:
            return found

    for candidate in client.search(title.name, kind=Kind.SHOW, year=title.year)[:1]:
        if title.year and candidate.get("first_air_date", "")[:4] not in ("", str(title.year)):
            continue
        return candidate
    return None


def enrich_title(client: TMDBClient, library: Library, title: TitleRow) -> bool:
    """Enrich one show in place. Returns whether TMDB knew it.

    Every season is walked, including season 0, so that specials the user has
    already logged keep their episode rows; up-next filters them out at query
    time rather than by omitting them here.
    """
    match = resolve_show(client, title)
    if match is None:
        return False

    detail = client.show(int(match["id"]))
    library.apply_enrichment(
        title.id,
        title_from_show(detail),
        enriched_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )

    for season in detail.get("seasons") or []:
        number = season.get("season_number")
        if number is None:
            continue
        try:
            payload = client.season(int(detail["id"]), int(number))
        except TMDBError:
            # A season listed on the show but missing its own endpoint is a
            # TMDB data gap, not a reason to abandon the rest of the show.
            continue
        for episode in episodes_from_season(payload):
            library.upsert_episode(title.id, episode)

    library.conn.commit()
    return True


def enrich(
    client: TMDBClient,
    library: Library,
    titles: Iterable[TitleRow],
    *,
    on_progress: Callable[[TitleRow, bool], None] | None = None,
) -> EnrichmentResult:
    result = EnrichmentResult(matched=[], unmatched=[])
    for title in titles:
        try:
            ok = enrich_title(client, library, title)
        except TMDBError:
            ok = False
        (result.matched if ok else result.unmatched).append(title.name)
        if on_progress is not None:
            on_progress(title, ok)
    return result
