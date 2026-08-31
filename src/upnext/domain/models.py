"""The vocabulary shared by the importer, the catalog and the API."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Kind(StrEnum):
    SHOW = "show"
    MOVIE = "movie"


class Status(StrEnum):
    """Where a title sits for the user.

    Deliberately four buckets and no "unwatched": a title with no relationship
    to the user has no state row at all.
    """

    WATCHING = "watching"
    COMPLETED = "completed"
    WATCHLIST = "watchlist"
    STOPPED = "stopped"


@dataclass(slots=True)
class Title:
    name: str
    kind: Kind = Kind.SHOW
    year: int | None = None
    tmdb_id: int | None = None
    tvdb_id: int | None = None
    imdb_id: str | None = None
    overview: str | None = None
    poster_path: str | None = None
    backdrop_path: str | None = None
    air_status: str | None = None
    first_air_date: str | None = None
    last_air_date: str | None = None
    total_episodes: int | None = None
    runtime: int | None = None


@dataclass(slots=True)
class Episode:
    season_number: int
    episode_number: int
    name: str | None = None
    overview: str | None = None
    air_date: str | None = None
    runtime: int | None = None
    still_path: str | None = None
    tmdb_id: int | None = None
    tvdb_id: int | None = None


@dataclass(slots=True)
class Watch:
    """One viewing. `episode` is None for a film."""

    watched_at: str
    episode: tuple[int, int] | None = None
    is_rewatch: bool = False
    source: str = "upnext"
    # The source's id for what was watched, where it has one. Distinguishes
    # two watches the source could not number — see schema.sql.
    source_episode_id: str | None = None


@dataclass(slots=True)
class TitleState:
    status: Status
    is_favorite: bool = False
    rating: int | None = None
    reported_watched: int | None = None
    followed_at: str | None = None


@dataclass(slots=True)
class ImportedTitle:
    """A title as reconstructed from an export, before it meets TMDB."""

    title: Title
    state: TitleState
    watches: list[Watch] = field(default_factory=list)


@dataclass(slots=True)
class TitleRow:
    """A stored title joined with the user's state and their counted progress.

    The read model, as opposed to `Title`, which is what a source says a title
    *is*. It lives here rather than in the store because enrichment and the API
    both speak it, and neither should import the repository to name its own
    argument types.
    """

    id: int
    kind: Kind
    name: str
    year: int | None
    tmdb_id: int | None
    tvdb_id: int | None
    poster_path: str | None
    air_status: str | None
    total_episodes: int | None
    status: Status | None
    is_favorite: bool
    rating: int | None
    reported_watched: int | None
    episodes_watched: int
    last_watched_at: str | None
