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


def connect(db_path: Path | str, *, same_thread_only: bool = True) -> sqlite3.Connection:
    """Open the library, creating the file and the schema if either is missing.

    ":memory:" is passed through untouched so tests can hold a whole library in
    RAM without a temporary directory.

    `same_thread_only=False` is for the HTTP layer and nothing else. FastAPI
    runs a sync dependency, the endpoint it feeds, and the dependency's teardown
    on three separately borrowed threadpool threads, so a connection opened per
    request is opened on one thread and used on another — which sqlite3 refuses
    by default. The three run in sequence and never overlap, so what the guard
    would be protecting against cannot happen; what it does instead is fail a
    request whenever the pool happens to hand out a different thread, which is
    most of them once a page asks for more than one endpoint at a time.
    """
    if db_path != ":memory:":
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        db_path = str(path)

    conn = sqlite3.connect(db_path, check_same_thread=same_thread_only)
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
    _drop_episode_confirmed_at(conn)
    _stop_a_deleted_episode_deleting_the_viewing(conn)
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


def _drop_episode_confirmed_at(conn: sqlite3.Connection) -> None:
    """Remove a column from a design that did not survive.

    An intermediate version marked each episode with when the catalog confirmed
    it, to tell an invented row from a real one. Keeping the two apart turned
    out to be better done by not inventing rows at all, and the column has had
    no reader since.
    """
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(episodes)")}
    if "confirmed_at" not in columns:
        return
    conn.execute("ALTER TABLE episodes DROP COLUMN confirmed_at")


def _stop_a_deleted_episode_deleting_the_viewing(conn: sqlite3.Connection) -> None:
    """Change `watches.episode_id` from ON DELETE CASCADE to SET NULL.

    Under the old shape a watch could not outlive its episode, because the
    episode was invented from the watch. Now the episode belongs to the catalog
    and the viewing does not: a title dropped from TMDB's list must unlink the
    watch, never delete it. That is the whole point of the reshape, and a
    library that migrated into it while keeping the old rule would quietly lose
    history the first time an episode went away.

    SQLite cannot alter a foreign key, so the table is rebuilt. The DDL is
    written out here rather than read from schema.sql on purpose: a migration
    is a historical fact and has to keep saying what it meant at the time, not
    follow the schema wherever it goes next.
    """
    row = conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'watches'").fetchone()
    if row is None or "ON DELETE SET NULL" in row["sql"]:
        return

    # PRAGMA foreign_keys is a no-op inside a transaction, and the rebuild has
    # to run with enforcement off or the DROP takes the rows with it.
    conn.commit()
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.executescript(
            """
            CREATE TABLE watches_rebuilt (
                id          INTEGER PRIMARY KEY,
                title_id    INTEGER NOT NULL REFERENCES titles (id) ON DELETE CASCADE,
                episode_id  INTEGER REFERENCES episodes (id) ON DELETE SET NULL,
                watched_at  TEXT    NOT NULL,
                is_rewatch  INTEGER NOT NULL DEFAULT 0,
                source_season  INTEGER,
                source_episode INTEGER,
                source_episode_id TEXT,
                source      TEXT    NOT NULL DEFAULT 'upnext'
            );

            INSERT INTO watches_rebuilt (id, title_id, episode_id, watched_at, is_rewatch,
                                         source_season, source_episode, source_episode_id, source)
                 SELECT id, title_id, episode_id, watched_at, is_rewatch,
                        source_season, source_episode, source_episode_id, source
                   FROM watches;

            DROP TABLE watches;
            ALTER TABLE watches_rebuilt RENAME TO watches;
            """
        )
        # The indexes went with the old table; schema.sql recreates them, which
        # is why migrations run before it rather than after.
        conn.commit()
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


@contextmanager
def open_library(db_path: Path | str) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
