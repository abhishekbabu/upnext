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
        conn.executescript(resources.files(__package__).joinpath("schema.sql").read_text(encoding="utf-8"))
    except sqlite3.DatabaseError as exc:
        conn.close()
        raise LibraryError(f"{path} cannot be opened as a library: {exc}") from exc
    return conn
