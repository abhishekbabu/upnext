"""The read API the front end will consume, and a JSON view of the library today."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import asdict
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query

from upnext.adapters.outbound.store.db import connect
from upnext.adapters.outbound.store.library import Library
from upnext.config.settings import Settings, load_settings
from upnext.domain.models import Kind, Status

app = FastAPI(title="upnext", version="0.1.0")


def get_settings() -> Settings:
    return load_settings()


def get_library(settings: Annotated[Settings, Depends(get_settings)]) -> Iterator[Library]:
    # One connection per request, closed on the way out: SQLite objects are not
    # safe to share across threads and FastAPI runs sync endpoints in a pool,
    # so a cached connection is not an option and a leaked one is a file handle
    # per request.
    conn = connect(settings.db_path)
    try:
        yield Library(conn)
    finally:
        conn.close()


LibraryDep = Annotated[Library, Depends(get_library)]


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/titles")
def list_titles(
    library: LibraryDep,
    status: Annotated[Status | None, Query()] = None,
    kind: Annotated[Kind | None, Query()] = None,
) -> list[dict]:
    return [asdict(row) for row in library.titles(status=status, kind=kind)]


@app.get("/api/titles/{title_id}")
def get_title(title_id: int, library: LibraryDep) -> dict:
    title = library.title(title_id)
    if title is None:
        raise HTTPException(status_code=404, detail="No such title")
    return {**asdict(title), "episodes": [dict(row) for row in library.episodes(title_id)]}


@app.get("/api/up-next")
def up_next(library: LibraryDep, limit: Annotated[int, Query(ge=1, le=100)] = 20) -> list[dict]:
    return library.up_next(limit=limit)


@app.get("/api/stats")
def stats(library: LibraryDep) -> dict:
    return library.stats()
