"""The interfaces the core depends on.

Ports live with the code that *uses* them, not with the code that implements
them. That is what keeps the dependency arrows pointing inward: the domain
names what it needs, and the adapters satisfy it. Nothing in this package
imports an adapter.

Every port speaks in `domain.models` types. A port that returned TMDB's JSON
would put the application back in the business of knowing what TMDB is, which
is the coupling this file exists to remove.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from upnext.domain.models import Episode, ImportedTitle, Title, TitleRow, TitleState, Watch


@dataclass(frozen=True)
class CatalogMatch:
    """A candidate the catalog offered for a title upnext already had.

    Carries the year so resolution can refuse a wrong one without a second
    round trip. `None` means the catalog does not know when it aired, which is
    not the same as disagreeing.
    """

    catalog_id: int
    name: str = ""
    year: int | None = None


@dataclass(frozen=True)
class CatalogShow:
    """Everything the catalog knows about one show, already translated.

    Episodes are every season the catalog serves, season 0 included: specials
    the user has logged keep their rows, and up-next filters them at query time
    rather than by never storing them.
    """

    title: Title
    episodes: list[Episode] = field(default_factory=list)


class Catalog(Protocol):
    """Where a title's real name, artwork and episode list come from."""

    def find_by_tvdb(self, tvdb_id: int) -> CatalogMatch | None:
        """The show behind a TheTVDB id, or None if the catalog has no mapping.

        An identity lookup rather than a guess, which is why resolution tries
        it before searching by name.
        """
        ...

    def search_shows(self, name: str, *, year: int | None = None) -> list[CatalogMatch]:
        """Candidates for a name, best first."""
        ...

    def fetch_show(self, catalog_id: int) -> CatalogShow:
        """The full record for one show.

        Raises:
            CatalogError: the catalog could not serve it.
        """
        ...


class WatchLibrary(Protocol):
    """The stored library, in the vocabulary of the domain.

    Narrower than the repository that implements it: this is what the use cases
    need, not everything the store can do. Reads that only an inbound adapter
    performs — the API's queries, `stats` — are deliberately absent.
    """

    def upsert_title(self, title: Title) -> int: ...

    def set_state(self, title_id: int, state: TitleState) -> None: ...

    def record_watch(self, title_id: int, watch: Watch) -> None: ...

    def upsert_episode(self, title_id: int, episode: Episode) -> int:
        """Store one episode of the catalog's list."""
        ...

    def title_by_tmdb_id(self, tmdb_id: int) -> TitleRow | None:
        """The stored title with this catalog id, if there is one."""
        ...

    def move_watches(self, *, source_id: int, target_id: int, season: int, as_season: int) -> int:
        """Reassign one source season's viewings to a different title."""
        ...

    def link_watches(self, title_id: int) -> int:
        """Match this title's recorded viewings to the episodes just stored.

        Returns how many found one. The rest are viewings of something the
        catalog's list does not contain, and keep the numbering the source gave
        them.
        """
        ...

    def apply_enrichment(self, title_id: int, title: Title, *, enriched_at: str) -> None: ...

    def commit(self) -> None:
        """Make everything written since the last commit durable.

        Named on the port because the use cases decide what a unit of work is —
        one import, one enriched title — and reaching through to a connection
        to say so would be the application knowing it is talking to SQLite.
        """
        ...


class ImportSource(Protocol):
    """A service whose export upnext can reconstruct a library from."""

    name: str
    """What the user types to select it: 'tvtime'."""

    def read(self, export_dir: Path) -> list[ImportedTitle]:
        """Parse an export folder. Never touches the network.

        Raises:
            ExportError: the folder is not an export this source recognises.
        """
        ...
