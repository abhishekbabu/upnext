"""SQLite connection handling, schema application and migrations."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from importlib import resources
from pathlib import Path

SCHEMA_RESOURCE = "schema.sql"


def read_schema() -> str:
    return resources.files("upnext.adapters.outbound.store").joinpath(SCHEMA_RESOURCE).read_text(encoding="utf-8")


def connect(db_path: Path | str) -> sqlite3.Connection:
    """Open the library, creating the file and the schema if either is missing.

    ":memory:" is passed through untouched so tests can hold a whole library in
    RAM without a temporary directory.
    """
    if db_path != ":memory:":
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        db_path = str(path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    # Foreign keys are off by default in SQLite and are per-connection, so the
    # ON DELETE CASCADE clauses in the schema are inert without this line.
    conn.execute("PRAGMA foreign_keys = ON")
    # Migrations run first. Applying the schema means creating this version's
    # indexes, and one of them is over columns an older library does not have
    # yet — so the reshaping has to happen before, not after.
    migrate(conn)
    conn.executescript(read_schema())
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    """Bring an existing library to the shape `schema.sql` is about to apply.

    `CREATE TABLE IF NOT EXISTS` does nothing to a table that already exists, so
    a column added to schema.sql never reaches a library someone already has.
    Every step here is idempotent, and every step runs on every connect — a
    database that does not exist yet has no tables to find, and a current one
    finds nothing to do.

    The library is derived data and can always be rebuilt by re-importing, but
    an enrichment run is hundreds of API calls, so migrating is worth the lines.
    """
    _reshape_watches_onto_the_catalog(conn)
    conn.commit()


def _reshape_watches_onto_the_catalog(conn: sqlite3.Connection) -> None:
    """Move the source's episode numbering off `episodes` and onto `watches`.

    An earlier design had an import invent an episode row for every watch it
    could number, which put two enumerations of the same show in one table:
    TMDB's, and whatever the exporting service used. Where they disagreed the
    library grew rows the catalog would never account for, and a completed
    Friends read 236 of 228.

    The reshape keeps every viewing and every date. What the export called the
    episode moves onto the watch, the invented rows go, and enrichment matches
    watches to real episodes afterwards. Re-importing would reach the same
    place, but an enrichment run is hundreds of API calls.
    """
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(watches)")}
    # Empty for a database being created right now, which has nothing to move.
    if not columns or "source_season" in columns:
        return

    conn.execute("ALTER TABLE watches ADD COLUMN source_season INTEGER")
    conn.execute("ALTER TABLE watches ADD COLUMN source_episode INTEGER")

    # The numbering is on the episode row the watch points at — which is where
    # it came from, whether that row was the catalog's or the import's.
    conn.execute(
        """
        UPDATE watches
           SET source_season  = (SELECT e.season_number  FROM episodes e WHERE e.id = watches.episode_id),
               source_episode = (SELECT e.episode_number FROM episodes e WHERE e.id = watches.episode_id)
         WHERE episode_id IS NOT NULL
        """
    )

    # Unlink before deleting: the old foreign key cascaded, so dropping these
    # rows first would take every viewing that pointed at one with them.
    conn.execute(
        "UPDATE watches SET episode_id = NULL WHERE episode_id IN (SELECT id FROM episodes WHERE tmdb_id IS NULL)"
    )
    conn.execute("DELETE FROM episodes WHERE tmdb_id IS NULL")

    # Replaced by watches_source_numbering, which schema.sql has already made.
    conn.execute("DROP INDEX IF EXISTS watches_episode_time")


@contextmanager
def open_library(db_path: Path | str) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
