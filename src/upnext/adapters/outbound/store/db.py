"""SQLite connection handling and schema application."""

from __future__ import annotations

import sqlite3
from importlib import resources
from pathlib import Path

from upnext.domain.errors import LibraryError


def connect(db_path: Path | str, *, same_thread_only: bool = True) -> sqlite3.Connection:
    """Open the library, creating the file and the schema if either is missing.

    `open_library` in `library.py` says when `same_thread_only` may be off.
    """
    # ":memory:" survives this: its parent is ".", which exists.
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        conn = sqlite3.connect(path, check_same_thread=same_thread_only)
    except sqlite3.Error as exc:
        raise LibraryError(f"{path} cannot be opened as a library: {exc}") from exc
    try:
        conn.row_factory = sqlite3.Row
        # Foreign keys are off by default in SQLite and are per-connection, so the
        # ON DELETE clauses in the schema are inert without this line.
        conn.execute("PRAGMA foreign_keys = ON")
        schema = resources.files(__package__).joinpath("schema.sql").read_text(encoding="utf-8")
        conn.executescript(schema)
        _upgrade(conn, schema)
    except sqlite3.DatabaseError as exc:
        conn.close()
        raise LibraryError(f"{path} cannot be opened as a library: {exc}") from exc
    return conn


def _upgrade(conn: sqlite3.Connection, schema: str) -> None:
    """Bring a library made by an older schema up to this one. `PRAGMA user_version` counts the steps.

    `CREATE TABLE IF NOT EXISTS` covers a new table, not a changed one, and
    SQLite cannot alter a CHECK in place. So a changed table is renamed aside,
    the schema run again to create it afresh, and its rows copied across — one
    script, so a failure rolls the whole step back.
    """
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version < 1:
        # 1: `watch_later` joins the statuses, and `status_pinned` the columns.
        (old,) = conn.execute("SELECT sql FROM sqlite_master WHERE name = 'title_state'").fetchone()
        if "watch_later" not in old:
            columns = "title_id, status, is_favorite, rating, reported_watched, followed_at"
            try:
                conn.executescript(
                    "BEGIN;"
                    "ALTER TABLE title_state RENAME TO title_state_v0;"
                    "DROP INDEX IF EXISTS title_state_status;"
                    f"{schema};"
                    f"INSERT INTO title_state ({columns}) SELECT {columns} FROM title_state_v0;"
                    "DROP TABLE title_state_v0;"
                    "COMMIT;"
                )
            except sqlite3.Error:
                conn.rollback()
                raise
        conn.execute("PRAGMA user_version = 1")
