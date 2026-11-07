"""SQLite connection handling and schema application."""

from __future__ import annotations

import sqlite3
from importlib import resources
from pathlib import Path


def connect(db_path: Path | str, *, same_thread_only: bool = True) -> sqlite3.Connection:
    """Open the library, creating the file and the schema if either is missing.

    ":memory:" is passed through untouched so tests can hold a whole library in
    RAM without a temporary directory. `open_library` in `library.py` says when
    `same_thread_only` may be off.
    """
    if db_path != ":memory:":
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        db_path = str(path)

    conn = sqlite3.connect(db_path, check_same_thread=same_thread_only)
    conn.row_factory = sqlite3.Row
    # Foreign keys are off by default in SQLite and are per-connection, so the
    # ON DELETE clauses in the schema are inert without this line.
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(resources.files(__package__).joinpath("schema.sql").read_text(encoding="utf-8"))
    return conn
