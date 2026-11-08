"""HTTP API for the web UI.

An inbound adapter like the CLI: it renders errors and owns transport, and
computes nothing. The repository returns domain types and the wire models below
name them for the client. `web/openapi.json` is generated from this module and
the client's types from that, so a field changed here is a typecheck failure in
the panel that reads it.

Serves the built front end from `web/dist` when it exists, so one process on one
port covers both. In development the front end runs its own dev server and calls
back here across the proxy configured in `web/vite.config.ts`.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi import Path as PathParam
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict
from starlette.types import Scope

from upnext import __version__
from upnext.adapters.outbound.store.library import Library, open_library
from upnext.config.settings import PROJECT_ROOT, Settings
from upnext.domain.errors import NotFoundError
from upnext.domain.models import Status

logger = logging.getLogger(__name__)

DIST = PROJECT_ROOT / "web" / "dist"


# Named after what the client does with them, not after the tables. Every
# field is one the UI actually reads: a response is a contract, and a field
# nothing consumes is a field nobody maintains. The domain types carry the rest.


class Wire(BaseModel):
    # Field docstrings become descriptions in the OpenAPI schema, and from
    # there comments on the client's generated types.
    model_config = ConfigDict(use_attribute_docstrings=True)


class Config(Wire):
    """What the client needs to know about this installation to render at all."""

    image_base: str
    """TMDB's artwork CDN. The library stores paths, so the client joins this to
    a `poster_path` with the size it wants — a render-time decision, and
    therefore the client's."""


class TitleSummary(Wire):
    """A title as a shelf sees it: enough for a poster and its progress."""

    id: int
    name: str
    year: int | None
    poster_path: str | None
    status: Status | None

    total_episodes: int | None
    """What the catalog says the whole run is, specials excluded."""

    episodes_watched: int
    """Distinct episodes watched that TMDB's list contains, specials excluded.
    The figure `total_episodes` is comparable to."""

    unmatched_watched: int
    """Distinct episodes watched that TMDB's list does not contain, specials
    included, counted by what the export called them. Real viewings of something TMDB numbers
    differently — the two together are the whole history."""

    enriched_at: str | None
    """Null until TMDB has answered for this title, which is what tells "TMDB
    does not list these" apart from "there is no list yet"."""


class TitleEpisode(Wire):
    id: int
    season_number: int
    episode_number: int
    name: str | None
    air_date: str | None

    watch_count: int
    """Viewings, so a rewatch is 2 rather than collapsing into "seen"."""

    marked_here: bool
    """Whether a viewing was marked in upnext, and so can be unmarked."""


class UnmatchedViewing(Wire):
    """Viewings of an episode TMDB's list does not contain, in the export's numbering.

    Rendered apart from the episode list rather than mixed into it: they are
    not episodes of this show as TMDB understands it.
    """

    season_number: int
    episode_number: int
    watch_count: int
    last_watched_at: str | None


class TitleDetail(TitleSummary):
    overview: str | None

    air_status: str | None
    """The show's own status at TMDB ("Ended", "Returning Series"), not the user's."""

    rating: int | None
    """Out of 10. A TV Time rating out of 5 is doubled on import."""

    episodes: list[TitleEpisode] = []
    unmatched: list[UnmatchedViewing] = []

    today: str = ""
    """Today in UTC, so the client can tell an episode that is out — and can be
    marked — from one that is not, without its own clock."""


class ShelfEpisode(Wire):
    """An episode beside its show's name and artwork."""

    title_id: int
    name: str
    poster_path: str | None
    episode_id: int
    season_number: int
    episode_number: int
    episode_name: str | None


class UpNextItem(ShelfEpisode):
    """The next unwatched episode of one show in progress."""

    last_watched_at: str | None
    air_date: str | None
    """When the episode aired, for sorting by the newest; null if TMDB has no date."""


class TimelineItem(ShelfEpisode):
    """One unwatched episode, recently out or still to come, of a show with watch history."""

    air_date: str


class Timeline(Wire):
    today: str
    """Today in UTC. Sent rather than left to the client, which would otherwise
    have to agree with the server about when today is — and so which episodes
    are out to be marked."""

    episodes: list[TimelineItem]


class Stats(Wire):
    watches: int
    distinct_episodes: int
    """History, not progress: matched and unmatched, specials included."""

    titles_watched: int
    first_watch: str | None
    last_watch: str | None

    known_minutes: int
    """A floor, not a total: nothing has a runtime before enrichment."""

    by_status: dict[Status, int]


def get_settings() -> Settings:
    return Settings()


def get_library(settings: Annotated[Settings, Depends(get_settings)]) -> Iterator[Library]:
    """One connection per request, closed on the way out.

    A cached connection is not an option, since FastAPI runs sync endpoints in
    a pool; see `open_library` for why this one may cross threads.
    """
    with open_library(settings.db_path, same_thread_only=False) as library:
        yield library


LibraryDep = Annotated[Library, Depends(get_library)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

app = FastAPI(title="upnext", version=__version__)


@app.get("/api/config")
def config(settings: SettingsDep) -> Config:
    return Config(image_base=settings.tmdb_image_base)


@app.get("/api/titles")
def list_titles(library: LibraryDep, status: Annotated[Status | None, Query()] = None) -> list[TitleSummary]:
    return [TitleSummary.model_validate(row, from_attributes=True) for row in library.titles(status=status)]


@app.get("/api/titles/{title_id}")
def get_title(title_id: Annotated[int, PathParam(gt=0, lt=2**63)], library: LibraryDep) -> TitleDetail:
    title = library.title(title_id)
    if title is None:
        raise HTTPException(status_code=404, detail="No such title")
    return TitleDetail.model_validate(title, from_attributes=True).model_copy(
        update={
            "today": _today().isoformat(),
            "episodes": [TitleEpisode.model_validate(row, from_attributes=True) for row in library.episodes(title_id)],
            "unmatched": [
                UnmatchedViewing.model_validate(row, from_attributes=True)
                for row in library.unmatched_watches(title_id)
            ],
        }
    )


class StatusChange(Wire):
    status: Status


@app.put("/api/titles/{title_id}/status", status_code=204)
def set_status(title_id: Annotated[int, PathParam(gt=0, lt=2**63)], change: StatusChange, library: LibraryDep) -> None:
    """File a title under a status. Kept over whatever a later re-import says."""
    try:
        library.set_status(title_id, change.status)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/up-next")
def up_next(library: LibraryDep) -> list[UpNextItem]:
    return [UpNextItem.model_validate(row, from_attributes=True) for row in library.up_next()]


def _today() -> date:
    # UTC because that is what everything else in upnext compares in, and an
    # air date carries no timezone of its own.
    return datetime.now(UTC).date()


RECENT = timedelta(days=30)
"""How far back the timeline reaches for episodes already out and not yet watched.
Older ones are the backlog, which is what up next is for."""


@app.get("/api/timeline")
def timeline(library: LibraryDep) -> Timeline:
    today = _today()
    return Timeline(
        today=today.isoformat(),
        episodes=[
            TimelineItem.model_validate(row, from_attributes=True)
            for row in library.timeline(since=(today - RECENT).isoformat())
        ],
    )


EpisodeId = Annotated[int, PathParam(gt=0, lt=2**63)]


@app.post("/api/episodes/{episode_id}/watch", status_code=204)
def mark_watched(episode_id: EpisodeId, library: LibraryDep) -> None:
    """Record a viewing now. Stamped in UTC, in the same shape imported timestamps take."""
    try:
        library.mark_watched(episode_id, watched_at=datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/api/episodes/{episode_id}/watch", status_code=204)
def unmark_watched(episode_id: EpisodeId, library: LibraryDep) -> None:
    """Remove the latest viewing marked in upnext. Imported history stays."""
    try:
        library.unmark_watched(episode_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/stats")
def stats(library: LibraryDep) -> Stats:
    return Stats.model_validate(library.stats(), from_attributes=True)


# Everything Vite writes into assets/ carries a content hash in its filename, so
# a changed file is a changed URL and the old one can be kept for good. The year
# is the convention rather than a considered duration; `immutable` is the half
# that matters, because it stops a reload revalidating what cannot have changed.
IMMUTABLE = {"cache-control": "public, max-age=31536000, immutable"}

# index.html is the opposite: its name never changes and its contents name this
# build's bundle. Cached without this, a browser holds yesterday's index.html —
# and with it yesterday's app — on a heuristic of its own choosing, and a
# rebuild does not reach anyone who has visited before. `no-cache` still lets it
# be stored and revalidated, which the ETag makes almost free.
REVALIDATE = {"cache-control": "no-cache"}


class ImmutableStatic(StaticFiles):
    """`StaticFiles`, but saying how long a content-hashed asset keeps."""

    def file_response(
        self,
        full_path: str | os.PathLike[str],
        stat_result: os.stat_result,
        scope: Scope,
        status_code: int = 200,
    ) -> Response:
        response = super().file_response(full_path, stat_result, scope, status_code)
        response.headers.update(IMMUTABLE)
        return response


def mount_web(app: FastAPI, dist: Path) -> None:
    """Serve the built front end, when there is one.

    Registered last so it cannot shadow an API route. Without a build the API
    still runs on its own — which is what the CLI's `serve` does before anyone
    has run `just web-build`.
    """
    if not dist.is_dir():
        logger.info("web/dist not built; serving the API only. Run `just ui` to build and serve it.")
        return

    app.mount("/assets", ImmutableStatic(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        """Any non-API path returns index.html; the client owns routing.

        An unmatched API path is a 404 rather than the page, because this
        handler is the last one tried: without the check, a client asking for a
        route that has been renamed gets index.html with a 200, and the failure
        surfaces as JSON that will not parse rather than as the missing route
        it is.
        """
        if path.startswith("api/"):
            raise HTTPException(status_code=404, detail=f"Unknown endpoint '/{path}'.")
        candidate = (dist / path).resolve()
        if path and candidate.is_relative_to(dist.resolve()) and candidate.is_file():
            return FileResponse(candidate, headers=REVALIDATE)
        return FileResponse(dist / "index.html", headers=REVALIDATE)


mount_web(app, DIST)
