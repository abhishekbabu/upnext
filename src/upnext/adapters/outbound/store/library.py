"""The SQLite repository behind the `WatchLibrary` port.

Speaks `domain.models` in both directions: nothing above this module handles a
`sqlite3.Row`. Which viewing is of which episode is `domain.matching`'s call;
this module only loads what it needs and writes down what it decided.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import asdict, fields
from pathlib import Path
from typing import TYPE_CHECKING

from upnext.adapters.outbound.store.db import connect
from upnext.domain.matching import CatalogEntry, match
from upnext.domain.models import (
    Episode,
    EpisodeRow,
    Kind,
    LibraryStats,
    ShelfEpisode,
    Status,
    Title,
    TitleRow,
    TitleState,
    UnmatchedWatch,
    Watch,
    in_status_order,
)

if TYPE_CHECKING:
    from _typeshed import DataclassInstance

TITLE_COLUMNS = tuple(f.name for f in fields(Title))
EPISODE_COLUMNS = tuple(f.name for f in fields(Episode))

# The columns of `titles` that enrichment is allowed to overwrite. `name` and
# `year` are not among them: an import names a title from the user's own
# history, and a bad TMDB match must not silently rewrite the library.
ENRICHABLE = (
    "tmdb_id",
    "imdb_id",
    "overview",
    "poster_path",
    "backdrop_path",
    "air_status",
    "first_air_date",
    "last_air_date",
    "total_episodes",
    "runtime",
)

# A title, the user's state and the two progress counts. Specials are excluded
# from `episodes_watched` because the catalog leaves season 0 out of the
# `total_episodes` it is measured against; `unmatched_watched` counts what the
# source called an episode, because that is all there is to count it by.
TITLE_ROWS = """
    SELECT t.*, s.status, s.is_favorite, s.rating, s.reported_watched,
           COUNT(DISTINCT CASE WHEN e.season_number > 0 THEN w.episode_id END) AS episodes_watched,
           COUNT(DISTINCT CASE WHEN w.episode_id IS NULL AND w.source_season > 0
                               THEN w.source_season || 'x' || w.source_episode END) AS unmatched_watched,
           MAX(w.watched_at) AS last_watched_at
    FROM titles t
    LEFT JOIN title_state s ON s.title_id = t.id
    LEFT JOIN watches w ON w.title_id = t.id
    LEFT JOIN episodes e ON e.id = w.episode_id
"""

SHELF_EPISODES = """
    SELECT t.id AS title_id, t.name, t.poster_path,
           e.id AS episode_id, e.season_number, e.episode_number, e.name AS episode_name, e.air_date,
           (SELECT MAX(w2.watched_at) FROM watches w2 WHERE w2.title_id = t.id) AS last_watched_at
    FROM titles t
    JOIN episodes e ON e.title_id = t.id
"""


@contextmanager
def open_library(db_path: Path | str, *, same_thread_only: bool = True) -> Generator[Library]:
    """The library at `db_path`, committed if the block finishes and closed either way.

    `same_thread_only=False` is for the HTTP layer and nothing else. FastAPI
    runs a sync dependency, the endpoint it feeds, and the dependency's teardown
    on three separately borrowed threadpool threads, so a connection opened per
    request is opened on one thread and used on another — which sqlite3 refuses
    by default. The three run in sequence and never overlap, so the guard has
    nothing to protect; what it does instead is fail a request whenever the pool
    hands out a different thread.
    """
    conn = connect(db_path, same_thread_only=same_thread_only)
    try:
        yield Library(conn)
        conn.commit()
    finally:
        conn.close()


class Library:
    """A repository over one SQLite connection.

    Every write is idempotent on the natural key, so re-importing an export or
    re-running enrichment converges instead of duplicating.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def commit(self) -> None:
        self.conn.commit()

    def upsert_title(self, title: Title) -> int:
        """Insert or update a title, returning its local id.

        Matching goes tmdb_id, then tvdb_id, then (kind, name, year) — widest
        identifier first, so a title that gains a tmdb_id during enrichment is
        still recognised as the same row on the next import.
        """
        params = asdict(title)
        existing = self._find_title_id(title)
        if existing is None:
            cur = self.conn.execute(
                f"INSERT INTO titles ({', '.join(TITLE_COLUMNS)}) VALUES ({', '.join(':' + c for c in TITLE_COLUMNS)})",
                params,
            )
            # sqlite3 types lastrowid as optional; an INSERT that returned
            # without one would have raised long before this line.
            assert cur.lastrowid is not None
            return cur.lastrowid

        # Only fill blanks. An import that knows nothing but a name must not
        # erase the artwork and overview a previous enrichment resolved.
        assignments = ", ".join(f"{col} = COALESCE({col}, :{col})" for col in ("year", *ENRICHABLE))
        self.conn.execute(f"UPDATE titles SET {assignments} WHERE id = :id", params | {"id": existing})
        return existing

    def apply_enrichment(self, title_id: int, title: Title, *, enriched_at: str) -> None:
        """Overwrite the catalog-owned columns with what the source of truth says."""
        assignments = ", ".join(f"{col} = :{col}" for col in ENRICHABLE)
        self.conn.execute(
            f"UPDATE titles SET {assignments}, enriched_at = :enriched_at WHERE id = :id",
            asdict(title) | {"id": title_id, "enriched_at": enriched_at},
        )

    def upsert_episode(self, title_id: int, episode: Episode) -> None:
        """Insert or update one episode of the catalog's list.

        Only enrichment reaches here. An import has a season and a number the
        exporting service used, and that goes on the watch.
        """
        columns = ("title_id", *EPISODE_COLUMNS)
        updates = ", ".join(
            f"{col} = COALESCE(excluded.{col}, episodes.{col})"
            for col in EPISODE_COLUMNS
            if col not in ("season_number", "episode_number")
        )
        self.conn.execute(
            f"""
            INSERT INTO episodes ({", ".join(columns)}) VALUES ({", ".join(":" + c for c in columns)})
            ON CONFLICT (title_id, season_number, episode_number) DO UPDATE SET {updates}
            """,
            asdict(episode) | {"title_id": title_id},
        )

    def record_watch(self, title_id: int, watch: Watch) -> None:
        """Record one viewing, in the source's own vocabulary.

        No episode row is created and none is looked up: whether the catalog
        agrees with the source's numbering is not knowable offline.
        `link_watches` joins the two once enrichment has an episode list.
        """
        if self._already_recorded(title_id, watch):
            return

        season, number = watch.episode or (None, None)
        self.conn.execute(
            """
            INSERT INTO watches (title_id, watched_at, is_rewatch, source,
                                 source_episode_id, source_season, source_episode)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (title_id, watch.watched_at, watch.is_rewatch, watch.source, watch.source_episode_id, season, number),
        )

    def _already_recorded(self, title_id: int, watch: Watch) -> bool:
        """Whether this exact viewing is in the library already.

        Identity is the source's own episode id where there is one, and the
        source's numbering plus the timestamp where there is not. The second
        form is why a bulk "mark season watched" — one timestamp across fifty
        episodes — does not collapse into a single row, and the first is why
        fifty watches the source declined to number do not either.

        On the source's numbering rather than on a resolved episode, because a
        re-import must converge whether or not enrichment has run since. The
        source's id is looked up under any title, because `upnext move` may
        have filed the viewing elsewhere since. Both mirror the unique indexes
        on `watches` in schema.sql.
        """
        if watch.source_episode_id is not None:
            sql = """
                SELECT 1 FROM watches
                WHERE source = ? AND source_episode_id = ? AND watched_at = ?
            """
            params: tuple[object, ...] = (watch.source, watch.source_episode_id, watch.watched_at)
        else:
            season, number = watch.episode or (None, None)
            sql = """
                SELECT 1 FROM watches
                WHERE title_id = ? AND source = ? AND watched_at = ?
                  AND source_season IS ? AND source_episode IS ? AND source_episode_id IS NULL
            """
            params = (title_id, watch.source, watch.watched_at, season, number)
        return self.conn.execute(sql, params).fetchone() is not None

    def link_watches(self, title_id: int) -> int:
        """Match this title's viewings to its stored episodes; returns how many found one."""
        catalog = [
            CatalogEntry(**row)
            for row in self.conn.execute(
                "SELECT id, season_number, episode_number, air_date FROM episodes WHERE title_id = ?", (title_id,)
            )
        ]
        numbered = self.conn.execute(
            """
            SELECT DISTINCT source_season, source_episode, episode_id FROM watches
             WHERE title_id = ? AND source_season IS NOT NULL
            """,
            (title_id,),
        ).fetchall()
        unlinked = {(r["source_season"], r["source_episode"]) for r in numbered if r["episode_id"] is None}
        linked = {(r["source_season"], r["source_episode"]): r["episode_id"] for r in numbered if r["episode_id"]}

        updated = 0
        for (season, number), episode_id in match(catalog, unlinked=unlinked, linked=linked).items():
            updated += self.conn.execute(
                """
                UPDATE watches SET episode_id = ?
                 WHERE title_id = ? AND episode_id IS NULL AND source_season = ? AND source_episode = ?
                """,
                (episode_id, title_id, season, number),
            ).rowcount
        return updated

    def set_state(self, title_id: int, state: TitleState) -> None:
        self.conn.execute(
            """
            INSERT INTO title_state (title_id, status, is_favorite, rating, reported_watched, followed_at, updated_at)
            VALUES (:title_id, :status, :is_favorite, :rating, :reported_watched, :followed_at, datetime('now'))
            ON CONFLICT (title_id) DO UPDATE SET
                status = excluded.status,
                is_favorite = excluded.is_favorite,
                rating = COALESCE(excluded.rating, title_state.rating),
                reported_watched = COALESCE(excluded.reported_watched, title_state.reported_watched),
                followed_at = COALESCE(excluded.followed_at, title_state.followed_at),
                updated_at = datetime('now')
            WHERE (title_state.status, title_state.is_favorite, title_state.rating,
                   title_state.reported_watched, title_state.followed_at)
               IS NOT (excluded.status, excluded.is_favorite,
                       COALESCE(excluded.rating, title_state.rating),
                       COALESCE(excluded.reported_watched, title_state.reported_watched),
                       COALESCE(excluded.followed_at, title_state.followed_at))
            """,
            asdict(state) | {"title_id": title_id},
        )

    def move_watches(self, *, source_id: int, target_id: int, season: int, as_season: int) -> int:
        """Reassign one source season's viewings to a different title.

        `episode_id` is cleared because the target's episode list is a
        different list — whatever these matched before means nothing there.
        """
        return self.conn.execute(
            """
            UPDATE watches
               SET title_id = :target_id, source_season = :as_season, episode_id = NULL
             WHERE title_id = :source_id AND source_season = :season
            """,
            {"target_id": target_id, "source_id": source_id, "season": season, "as_season": as_season},
        ).rowcount

    def titles(self, *, status: Status | None = None) -> list[TitleRow]:
        if status is None:
            return self._title_rows()
        return self._title_rows("s.status = ?", (status,))

    def title(self, title_id: int) -> TitleRow | None:
        return next(iter(self._title_rows("t.id = ?", (title_id,))), None)

    def title_by_tmdb_id(self, tmdb_id: int) -> TitleRow | None:
        return next(iter(self._title_rows("t.kind = ? AND t.tmdb_id = ?", (Kind.SHOW, tmdb_id))), None)

    def needing_enrichment(self, *, limit: int | None = None) -> list[TitleRow]:
        return self._title_rows("t.enriched_at IS NULL", order="t.name", limit=limit)

    def count_titles(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) AS n FROM titles").fetchone()["n"])

    def _title_rows(
        self,
        where: str = "1",
        params: tuple[object, ...] = (),
        *,
        order: str = "last_watched_at DESC NULLS LAST, t.name",
        limit: int | None = None,
    ) -> list[TitleRow]:
        # SQLite reads a negative LIMIT as none at all, so the limit stays a
        # bound parameter rather than text spliced into the statement.
        rows = self.conn.execute(
            f"{TITLE_ROWS} WHERE {where} GROUP BY t.id ORDER BY {order} LIMIT ?",
            (*params, limit or -1),
        ).fetchall()
        return [
            _from_row(
                TitleRow,
                row,
                kind=Kind(row["kind"]),
                status=Status(row["status"]) if row["status"] else None,
                is_favorite=bool(row["is_favorite"]),
            )
            for row in rows
        ]

    def episodes(self, title_id: int) -> list[EpisodeRow]:
        rows = self.conn.execute(
            """
            SELECT e.*, COUNT(w.id) AS watch_count, MAX(w.watched_at) AS last_watched_at
            FROM episodes e
            LEFT JOIN watches w ON w.episode_id = e.id
            WHERE e.title_id = ?
            GROUP BY e.id
            ORDER BY e.season_number, e.episode_number
            """,
            (title_id,),
        ).fetchall()
        return [_from_row(EpisodeRow, row) for row in rows]

    def unmatched_watches(self, title_id: int) -> list[UnmatchedWatch]:
        """Viewings this title's catalog episode list does not account for.

        Grouped by what the source called the episode, so a rewatch is one row
        with a count rather than two rows. Ordered by the source's numbering,
        which is the order they were watched in for anyone who watched in order.
        """
        rows = self.conn.execute(
            """
            SELECT source_season AS season_number, source_episode AS episode_number,
                   COUNT(*) AS watch_count, MAX(watched_at) AS last_watched_at
            FROM watches
            WHERE title_id = ? AND episode_id IS NULL AND source_season IS NOT NULL
            GROUP BY source_season, source_episode
            ORDER BY source_season, source_episode
            """,
            (title_id,),
        ).fetchall()
        return [_from_row(UnmatchedWatch, row) for row in rows]

    def up_next(self, limit: int) -> list[ShelfEpisode]:
        """The next unwatched episode of every show currently being watched.

        "Next" is the lowest-numbered episode with no watch against it, which
        is the only definition that survives a viewer who skipped around — the
        highest watched episode plus one would silently swallow the gap.
        Season 0 is specials at every source, and never the next thing to watch.
        """
        rows = self.conn.execute(
            f"""
            {SHELF_EPISODES}
            JOIN title_state s ON s.title_id = t.id AND s.status = ?
            WHERE e.id = (
                  SELECT e2.id FROM episodes e2
                  WHERE e2.title_id = t.id AND e2.season_number > 0
                    AND NOT EXISTS (SELECT 1 FROM watches w WHERE w.episode_id = e2.id)
                  ORDER BY e2.season_number, e2.episode_number
                  LIMIT 1
              )
            ORDER BY last_watched_at DESC NULLS LAST
            LIMIT ?
            """,
            (Status.WATCHING, limit),
        ).fetchall()
        return [_from_row(ShelfEpisode, row) for row in rows]

    def airing_next(self, today: str, limit: int) -> list[ShelfEpisode]:
        """Episodes airing today or later, of shows with watch history, soonest first.

        A schedule rather than a backlog, which is why it is a separate query
        from `up_next`: that one answers "what do I put on now" and is ordered
        by what was watched most recently, this one answers "what is coming"
        and is ordered by the calendar.

        "Shows I have seen" is watch history rather than `status`, because
        status does not survive contact with a real library — a show whose new
        season is a month out is usually filed `stopped` or `completed`, having
        been finished. History is the fact; the status is an opinion about it.

        `today` is the caller's, not `date('now')`, so the boundary it draws —
        an episode airing today is upcoming, yesterday's is not — can be pinned
        in a test.
        """
        rows = self.conn.execute(
            f"""
            {SHELF_EPISODES}
            -- Air dates are stored as the catalog wrote them, always YYYY-MM-DD,
            -- so lexicographic order is chronological order. A null air date is
            -- an episode TMDB has not scheduled, and never compares true here.
            WHERE e.air_date >= ?
              AND e.season_number > 0
              AND EXISTS (SELECT 1 FROM watches w WHERE w.title_id = t.id)
            ORDER BY e.air_date, t.name, e.season_number, e.episode_number
            LIMIT ?
            """,
            (today, limit),
        ).fetchall()
        return [_from_row(ShelfEpisode, row) for row in rows]

    def stats(self) -> LibraryStats:
        totals = self.conn.execute(
            """
            SELECT COUNT(*) AS watches,
                   COUNT(DISTINCT CASE
                       WHEN episode_id IS NOT NULL THEN 'e' || episode_id
                       WHEN source_season IS NOT NULL
                           THEN 'u' || title_id || 'x' || source_season || 'x' || source_episode
                   END) AS episodes_watched,
                   COUNT(DISTINCT title_id) AS titles_watched,
                   MIN(watched_at) AS first_watch,
                   MAX(watched_at) AS last_watch,
                   (SELECT COALESCE(SUM(COALESCE(e.runtime, t.runtime)), 0)
                      FROM watches w
                      JOIN titles t ON t.id = w.title_id
                      LEFT JOIN episodes e ON e.id = w.episode_id) AS known_minutes
            FROM watches
            """
        ).fetchone()
        counts = dict(self.conn.execute("SELECT status, COUNT(*) FROM title_state GROUP BY status").fetchall())
        return _from_row(LibraryStats, totals, by_status=in_status_order(counts))

    def _find_title_id(self, title: Title) -> int | None:
        for column, value in (("tmdb_id", title.tmdb_id), ("tvdb_id", title.tvdb_id), ("name", title.name)):
            if value is None:
                continue
            sql = f"SELECT id FROM titles WHERE kind = ? AND {column} = ?"
            params: tuple[object, ...] = (title.kind, value)
            if column == "name":
                sql += " AND year IS ?"
                params += (title.year,)
            if row := self.conn.execute(sql, params).fetchone():
                return int(row["id"])
        return None


def _from_row[T: DataclassInstance](cls: type[T], row: sqlite3.Row, **converted: object) -> T:
    """`cls` built from the row's columns of the same names, with `converted` taking precedence."""
    return cls(**{f.name: row[f.name] for f in fields(cls) if f.name not in converted} | converted)
