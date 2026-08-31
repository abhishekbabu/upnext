"""SQLite connection handling and schema application."""

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
    conn.executescript(read_schema())
    return conn


@contextmanager
def open_library(db_path: Path | str) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
