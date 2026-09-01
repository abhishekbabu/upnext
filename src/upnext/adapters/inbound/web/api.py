"""HTTP API for the web UI.

An inbound adapter like the CLI: it renders errors and owns transport, and
computes nothing. The repository returns domain types and the wire models below
name them for the client, so a field added to `TitleRow` is a typecheck failure
in `web/src/lib/api.ts` rather than an `undefined` at runtime.

Serves the built front end from `web/dist` when it exists, so one process on one
port covers both. In development the front end runs its own dev server and calls
back here across the proxy configured in `web/vite.config.ts`.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from upnext.adapters.outbound.store.db import connect
from upnext.adapters.outbound.store.library import Library
from upnext.config.settings import PROJECT_ROOT, Settings, load_settings
from upnext.domain.models import Kind, Status

logger = logging.getLogger(__name__)

DIST = PROJECT_ROOT / "web" / "dist"


# ── wire types ──────────────────────────────────────────────────────────
# Named after what the client does with them, not after the tables. Every
# field is one the UI actually reads: a response is a contract, and a field
# nothing consumes is a field nobody maintains.


class Config(BaseModel):
    """What the client needs to know about this installation to render at all."""

    image_base: str
    """TMDB's artwork CDN. The library stores paths, so the client joins this to
    a `poster_path` with the size it wants — which is a render-time decision and
    therefore the client's, not the server's."""


class TitleSummary(BaseModel):
    """A title as a shelf sees it: enough for a poster and its progress."""

    id: int
    kind: Kind
    name: str
    year: int | None = None
    poster_path: str | None = None
    air_status: str | None = None
    total_episodes: int | None = None
    status: Status | None = None
    is_favorite: bool = False
    rating: int | None = None

    episodes_watched: int = 0
    """Distinct episodes watched that TMDB's list contains, specials excluded.
    The figure `total_episodes` is comparable to."""

    unmatched_watched: int = 0
    """Distinct episodes watched that TMDB's list does not contain, counted by
    what the export called them. Real viewings of something TMDB numbers
    differently — the two together are the whole history."""

    enriched_at: str | None = None
    """Null until TMDB has answered for this title, which is what tells "TMDB
    does not list these" apart from "there is no list yet"."""

    last_watched_at: str | None = None


class TitleEpisode(BaseModel):
    """One episode of a title, with how often it has been watched."""

    id: int
    season_number: int
    episode_number: int
    name: str | None = None
    overview: str | None = None
    air_date: str | None = None
    runtime: int | None = None
    still_path: str | None = None
    watch_count: int = 0
    last_watched_at: str | None = None


class UnmatchedViewing(BaseModel):
    """Viewings of an episode TMDB's list does not contain.

    Rendered apart from the episode list rather than mixed into it: they are
    not episodes of this show as TMDB understands it, and putting them in the
    list would be putting the export's numbering back into the catalog's.
    """

    season_number: int
    episode_number: int
    watch_count: int
    last_watched_at: str | None = None


class TitleDetail(TitleSummary):
    overview: str | None = None
    backdrop_path: str | None = None
    first_air_date: str | None = None
    last_air_date: str | None = None
    runtime: int | None = None
    tmdb_id: int | None = None
    imdb_id: str | None = None
    episodes: list[TitleEpisode] = []
    unmatched: list[UnmatchedViewing] = []


class UpNextItem(BaseModel):
    """The next unwatched episode of one show in progress."""

    title_id: int
    name: str
    kind: Kind
    year: int | None = None
    poster_path: str | None = None
    episode_id: int
    season_number: int
    episode_number: int
    episode_name: str | None = None
    air_date: str | None = None
    still_path: str | None = None
    last_watched_at: str | None = None


class AiringItem(BaseModel):
    """One episode airing today or later, of a show with watch history.

    Same shape as `UpNextItem` and deliberately a separate model: they answer
    different questions, and `air_date` is the whole point here rather than an
    incidental fact, so it is required.
    """

    title_id: int
    name: str
    kind: Kind
    year: int | None = None
    poster_path: str | None = None
    episode_id: int
    season_number: int
    episode_number: int
    episode_name: str | None = None
    air_date: str
    still_path: str | None = None
    last_watched_at: str | None = None


class Stats(BaseModel):
    watches: int
    episodes_watched: int
    titles_watched: int
    first_watch: str | None = None
    last_watch: str | None = None
    known_minutes: int
    """A floor, not a total: only enriched episodes carry a runtime."""

    by_status: dict[str, int]


def get_settings() -> Settings:
    return load_settings()


def get_library(settings: Annotated[Settings, Depends(get_settings)]) -> Iterator[Library]:
    # One connection per request, closed on the way out: SQLite objects are not
    # safe to share across threads and FastAPI runs sync endpoints in a pool,
    # so a cached connection is not an option and a leaked one is a file handle
    # per request.
    #
    # `same_thread_only=False` because this request's three stages — building
    # the dependency, running the endpoint, closing it again — are each handed
    # a thread from that pool, and sqlite3's own check cannot tell them apart
    # from genuine concurrent use. They run one after another; nothing here is
    # shared with another request.
    conn = connect(settings.db_path, same_thread_only=False)
    try:
        yield Library(conn)
    finally:
        conn.close()


LibraryDep = Annotated[Library, Depends(get_library)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

app = FastAPI(title="upnext", version="0.1.0")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/config")
def config(settings: SettingsDep) -> Config:
    return Config(image_base=settings.tmdb_image_base)


@app.get("/api/titles")
def list_titles(
    library: LibraryDep,
    status: Annotated[Status | None, Query()] = None,
    kind: Annotated[Kind | None, Query()] = None,
) -> list[TitleSummary]:
    return [TitleSummary.model_validate(row, from_attributes=True) for row in library.titles(status=status, kind=kind)]


@app.get("/api/titles/{title_id}")
def get_title(title_id: int, library: LibraryDep) -> TitleDetail:
    title = library.title(title_id)
    if title is None:
        raise HTTPException(status_code=404, detail="No such title")
    detail = TitleDetail.model_validate(title, from_attributes=True)
    detail.episodes = [TitleEpisode.model_validate(row, from_attributes=True) for row in library.episodes(title_id)]
    detail.unmatched = [
        UnmatchedViewing.model_validate(row, from_attributes=True) for row in library.unmatched_watches(title_id)
    ]
    return detail


@app.get("/api/up-next")
def up_next(library: LibraryDep, limit: Annotated[int, Query(ge=1, le=100)] = 20) -> list[UpNextItem]:
    return [UpNextItem.model_validate(row) for row in library.up_next(limit=limit)]


@app.get("/api/airing")
def airing(library: LibraryDep, limit: Annotated[int, Query(ge=1, le=100)] = 20) -> list[AiringItem]:
    # Today is decided here rather than in SQL so the query stays testable
    # against a fixed calendar. UTC because that is what everything else in
    # upnext compares in, and an air date carries no timezone of its own.
    today = datetime.now(UTC).date().isoformat()
    return [AiringItem.model_validate(row) for row in library.airing_next(today, limit=limit)]


@app.get("/api/stats")
def stats(library: LibraryDep) -> Stats:
    return Stats.model_validate(library.stats())


def mount_web() -> None:
    """Serve the built front end, when there is one.

    Registered last so it cannot shadow an API route. Without a build the API
    still runs on its own — which is what the CLI's `serve` does before anyone
    has run `just web-build`.
    """
    if not DIST.is_dir():
        logger.info("web/dist not built; serving the API only. Run `just ui` to build and serve it.")
        return

    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> Any:
        """Any non-API path returns index.html; the client owns routing.

        An unmatched API path is a 404 rather than the page, because this
        handler is the last one tried: without the check, a client asking for a
        route that has been renamed gets index.html with a 200, and the failure
        surfaces as JSON that will not parse rather than as the missing route
        it is.
        """
        if path.startswith("api/"):
            raise HTTPException(status_code=404, detail=f"Unknown endpoint '/{path}'.")
        candidate = DIST / path
        if path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(DIST / "index.html")


mount_web()
