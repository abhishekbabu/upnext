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

    Carries every catalog column, not just the ones a shelf draws. What reaches
    the client is decided by the response model, and a field the row silently
    drops is a field the API promises and never sends.
    """

    id: int
    kind: Kind
    name: str
    year: int | None
    tmdb_id: int | None
    tvdb_id: int | None
    imdb_id: str | None
    overview: str | None
    poster_path: str | None
    backdrop_path: str | None
    air_status: str | None
    first_air_date: str | None
    last_air_date: str | None
    total_episodes: int | None
    runtime: int | None
    status: Status | None
    is_favorite: bool
    rating: int | None
    reported_watched: int | None

    episodes_watched: int
    """Distinct episodes watched, specials excluded.

    Excluded because `total_episodes` is the catalog's own count and every
    catalog leaves season 0 out of it. Counting specials here and not there
    makes the pair a nonsense — a show whose special you watched reads 33 of
    32 — so the numerator follows the denominator. It is also the same rule
    up-next already applies: season 0 is never the next thing to watch.

    Counts only episodes matched to the catalog's list, which is what makes it
    comparable to `total_episodes` at all. Viewings the list cannot account for
    are `unmatched_watched`, and the two together are the whole history.
    """

    unmatched_watched: int
    """Distinct episodes watched that the catalog's list does not contain.

    Counted by what the source called them, because that is all there is to
    count by. Not an error and not a gap to be tidied away: it is what a real
    disagreement looks like. TheTVDB splits eight double-length Friends
    episodes TMDB counts once; TV Time files Bly Manor as a second season of a
    title TMDB ends at one; Sidemen Sundays is numbered by year at one and
    1..N at the other, so not one of 320 viewings matches. Every one of those
    watches happened.

    Everything before enrichment is unmatched, because nothing has been
    matched yet — read it with `enriched_at`, never alone.
    """

    enriched_at: str | None
    """When the catalog last answered for this title, or None if never.

    What separates "the catalog's list does not contain these" from "there is
    no list yet", which are the same absence in the data and opposite
    statements to a reader.
    """

    last_watched_at: str | None


@dataclass(slots=True)
class EpisodeRow:
    """A stored episode with what the user has done to it.

    To `Episode` what `TitleRow` is to `Title`: the catalog's facts plus the
    library's own. Every one of these is an episode the catalog listed — an
    import never writes to that table — so there is no provenance to carry.
    """

    id: int
    season_number: int
    episode_number: int
    name: str | None = None
    overview: str | None = None
    air_date: str | None = None
    runtime: int | None = None
    still_path: str | None = None

    watch_count: int = 0
    """Viewings, not a flag: a rewatch is 2, so the count survives the trip."""

    last_watched_at: str | None = None


@dataclass(slots=True)
class UnmatchedWatch:
    """Viewings of an episode the catalog's list does not contain.

    All that survives of them is what the source called the episode, which is
    exactly why it is kept on the watch: the catalog cannot supply a name for
    something it does not believe exists, and dropping the numbering would
    leave a bare date.
    """

    season_number: int
    episode_number: int
    watch_count: int
    last_watched_at: str | None = None
