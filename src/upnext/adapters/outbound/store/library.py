"""The SQLite repository behind the `WatchLibrary` port.

Speaks `domain.models` in both directions: nothing above this module handles a
`sqlite3.Row`, and nothing in it decides policy.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence

from upnext.domain.models import Episode, Kind, Status, Title, TitleRow, TitleState, Watch

# The columns of `titles` that enrichment is allowed to overwrite. `name` and
# `year` are not among them by default: an import names a title from the user's
# own history, and a bad TMDB match should not silently rewrite the library.
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


class Library:
    """A thin repository over the SQLite connection.

    Every write is idempotent on the natural key, so re-importing an export or
    re-running enrichment converges instead of duplicating.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def commit(self) -> None:
        """Close the current unit of work. The caller decides where one ends."""
        self.conn.commit()

    # ---------------------------------------------------------------- writes

    def upsert_title(self, title: Title) -> int:
        """Insert or update a title, returning its local id.

        Matching goes tmdb_id, then tvdb_id, then (kind, name, year) — widest
        identifier first, so a title that gains a tmdb_id during enrichment is
        still recognised as the same row on the next import.
        """
        existing = self._find_title_id(title)
        if existing is None:
            cur = self.conn.execute(
                """
                INSERT INTO titles (kind, name, year, tmdb_id, tvdb_id, imdb_id, overview,
                                    poster_path, backdrop_path, air_status, first_air_date,
                                    last_air_date, total_episodes, runtime)
                VALUES (:kind, :name, :year, :tmdb_id, :tvdb_id, :imdb_id, :overview,
                        :poster_path, :backdrop_path, :air_status, :first_air_date,
                        :last_air_date, :total_episodes, :runtime)
                """,
                _title_params(title),
            )
            # sqlite3 types lastrowid as optional; an INSERT that returned
            # without one would have raised long before this line.
            assert cur.lastrowid is not None
            return cur.lastrowid

        # Only fill blanks. An import that knows nothing but a name must not
        # erase the artwork and overview a previous enrichment resolved.
        params = _title_params(title)
        assignments = [f"{col} = COALESCE({col}, :{col})" for col in ("year", *ENRICHABLE)]
        self.conn.execute(
            f"UPDATE titles SET {', '.join(assignments)} WHERE id = :id",
            {**params, "id": existing},
        )
        return existing

    def apply_enrichment(self, title_id: int, title: Title, *, enriched_at: str) -> None:
        """Overwrite the catalog-owned columns with what the source of truth says."""
        params = _title_params(title)
        assignments = ", ".join(f"{col} = :{col}" for col in ENRICHABLE)
        self.conn.execute(
            f"UPDATE titles SET {assignments}, enriched_at = :enriched_at WHERE id = :id",
            {**params, "id": title_id, "enriched_at": enriched_at},
        )

    def upsert_episode(self, title_id: int, episode: Episode) -> int:
        self.conn.execute(
            """
            INSERT INTO episodes (title_id, season_number, episode_number, name, overview,
                                  air_date, runtime, still_path, tmdb_id, tvdb_id)
            VALUES (:title_id, :season_number, :episode_number, :name, :overview,
                    :air_date, :runtime, :still_path, :tmdb_id, :tvdb_id)
            ON CONFLICT (title_id, season_number, episode_number) DO UPDATE SET
                name = COALESCE(excluded.name, episodes.name),
                overview = COALESCE(excluded.overview, episodes.overview),
                air_date = COALESCE(excluded.air_date, episodes.air_date),
                runtime = COALESCE(excluded.runtime, episodes.runtime),
                still_path = COALESCE(excluded.still_path, episodes.still_path),
                tmdb_id = COALESCE(excluded.tmdb_id, episodes.tmdb_id),
                tvdb_id = COALESCE(excluded.tvdb_id, episodes.tvdb_id)
            """,
            {
                "title_id": title_id,
                "season_number": episode.season_number,
                "episode_number": episode.episode_number,
                "name": episode.name,
                "overview": episode.overview,
                "air_date": episode.air_date,
                "runtime": episode.runtime,
                "still_path": episode.still_path,
                "tmdb_id": episode.tmdb_id,
                "tvdb_id": episode.tvdb_id,
            },
        )
        row = self.conn.execute(
            "SELECT id FROM episodes WHERE title_id = ? AND season_number = ? AND episode_number = ?",
            (title_id, episode.season_number, episode.episode_number),
        ).fetchone()
        return int(row["id"])

    def record_watch(self, title_id: int, watch: Watch) -> None:
        """Record one viewing, creating a placeholder episode if it is unknown.

        The placeholder matters: an export names episodes by season and number
        long before enrichment can give them titles, and dropping those watches
        until TMDB has been consulted would make the import worthless offline.
        """
        episode_id = None
        if watch.episode is not None:
            season, number = watch.episode
            episode_id = self.upsert_episode(title_id, Episode(season_number=season, episode_number=number))

        if self._already_recorded(title_id, episode_id, watch):
            return

        self.conn.execute(
            """
            INSERT INTO watches (title_id, episode_id, watched_at, is_rewatch, source, source_episode_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                title_id,
                episode_id,
                watch.watched_at,
                int(watch.is_rewatch),
                watch.source,
                watch.source_episode_id,
            ),
        )

    def _already_recorded(self, title_id: int, episode_id: int | None, watch: Watch) -> bool:
        """Whether this exact viewing is in the library already.

        Identity is the source's own episode id where there is one, and the
        episode plus timestamp where there is not. The second form is why a
        bulk "mark season watched" — one timestamp across fifty episodes — does
        not collapse into a single row, and the first is why fifty watches the
        source declined to number do not either.
        """
        if watch.source_episode_id is not None:
            sql = """
                SELECT 1 FROM watches
                WHERE title_id = ? AND source = ? AND source_episode_id = ? AND watched_at = ?
            """
            params: tuple = (title_id, watch.source, watch.source_episode_id, watch.watched_at)
        else:
            sql = """
                SELECT 1 FROM watches
                WHERE title_id = ? AND source = ? AND watched_at = ?
                  AND episode_id IS ? AND source_episode_id IS NULL
            """
            params = (title_id, watch.source, watch.watched_at, episode_id)
        return self.conn.execute(sql, params).fetchone() is not None

    def set_state(self, title_id: int, state: TitleState) -> None:
        self.conn.execute(
            """
            INSERT INTO title_state (title_id, status, is_favorite, rating, reported_watched, followed_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT (title_id) DO UPDATE SET
                status = excluded.status,
                is_favorite = excluded.is_favorite,
                rating = COALESCE(excluded.rating, title_state.rating),
                reported_watched = COALESCE(excluded.reported_watched, title_state.reported_watched),
                followed_at = COALESCE(excluded.followed_at, title_state.followed_at),
                updated_at = datetime('now')
            """,
            (
                title_id,
                str(state.status),
                int(state.is_favorite),
                state.rating,
                state.reported_watched,
                state.followed_at,
            ),
        )

    # ----------------------------------------------------------------- reads

    def titles(self, *, status: Status | None = None, kind: Kind | None = None) -> list[TitleRow]:
        where, params = [], {}
        if status is not None:
            where.append("s.status = :status")
            params["status"] = str(status)
        if kind is not None:
            where.append("t.kind = :kind")
            params["kind"] = str(kind)
        clause = f"WHERE {' AND '.join(where)}" if where else ""

        rows = self.conn.execute(
            f"""
            SELECT t.*, s.status, s.is_favorite, s.rating, s.reported_watched,
                   COUNT(DISTINCT w.episode_id) AS episodes_watched,
                   MAX(w.watched_at) AS last_watched_at
            FROM titles t
            LEFT JOIN title_state s ON s.title_id = t.id
            LEFT JOIN watches w ON w.title_id = t.id
            {clause}
            GROUP BY t.id
            ORDER BY last_watched_at DESC NULLS LAST, t.name
            """,
            params,
        ).fetchall()
        return [_title_row(row) for row in rows]

    def title(self, title_id: int) -> TitleRow | None:
        row = self.conn.execute(
            """
            SELECT t.*, s.status, s.is_favorite, s.rating, s.reported_watched,
                   COUNT(DISTINCT w.episode_id) AS episodes_watched,
                   MAX(w.watched_at) AS last_watched_at
            FROM titles t
            LEFT JOIN title_state s ON s.title_id = t.id
            LEFT JOIN watches w ON w.title_id = t.id
            WHERE t.id = ?
            GROUP BY t.id
            """,
            (title_id,),
        ).fetchone()
        return _title_row(row) if row else None

    def episodes(self, title_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
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

    def up_next(self, limit: int = 20) -> list[dict]:
        """The next unwatched episode of every show currently being watched.

        "Next" is the lowest-numbered episode with no watch against it, which
        is the only definition that survives a viewer who skipped around — the
        highest watched episode plus one would silently swallow the gap.
        """
        rows = self.conn.execute(
            """
            SELECT t.id AS title_id, t.name, t.kind, t.poster_path, t.year,
                   e.id AS episode_id, e.season_number, e.episode_number, e.name AS episode_name,
                   e.air_date, e.still_path,
                   (SELECT MAX(w2.watched_at) FROM watches w2 WHERE w2.title_id = t.id) AS last_watched_at
            FROM titles t
            JOIN title_state s ON s.title_id = t.id AND s.status = 'watching'
            JOIN episodes e ON e.title_id = t.id
            WHERE NOT EXISTS (SELECT 1 FROM watches w WHERE w.episode_id = e.id)
              -- Season 0 is specials at every source; they are not the next thing to watch.
              AND e.season_number > 0
              AND e.id = (
                  SELECT e2.id FROM episodes e2
                  WHERE e2.title_id = t.id AND e2.season_number > 0
                    AND NOT EXISTS (SELECT 1 FROM watches w2 WHERE w2.episode_id = e2.id)
                  ORDER BY e2.season_number, e2.episode_number
                  LIMIT 1
              )
            ORDER BY last_watched_at DESC NULLS LAST
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def stats(self) -> dict:
        totals = self.conn.execute(
            """
            SELECT COUNT(*) AS watches,
                   COUNT(DISTINCT episode_id) AS episodes,
                   COUNT(DISTINCT title_id) AS titles,
                   MIN(watched_at) AS first_watch,
                   MAX(watched_at) AS last_watch
            FROM watches
            """
        ).fetchone()
        by_status = self.conn.execute(
            "SELECT status, COUNT(*) AS n FROM title_state GROUP BY status ORDER BY n DESC"
        ).fetchall()
        # Only enriched episodes carry a runtime, so this is a floor on time
        # spent rather than a total, and is labelled that way in the UI.
        minutes = self.conn.execute(
            """
            SELECT COALESCE(SUM(COALESCE(e.runtime, t.runtime)), 0) AS minutes
            FROM watches w
            JOIN titles t ON t.id = w.title_id
            LEFT JOIN episodes e ON e.id = w.episode_id
            """
        ).fetchone()
        return {
            "watches": totals["watches"],
            "episodes_watched": totals["episodes"],
            "titles_watched": totals["titles"],
            "first_watch": totals["first_watch"],
            "last_watch": totals["last_watch"],
            "known_minutes": minutes["minutes"],
            "by_status": {row["status"]: row["n"] for row in by_status},
        }

    def count_titles(self) -> int:
        """How many titles the library holds at all, enriched or not."""
        return int(self.conn.execute("SELECT COUNT(*) AS n FROM titles").fetchone()["n"])

    def needing_enrichment(self, *, limit: int | None = None) -> list[TitleRow]:
        rows = self.conn.execute(
            f"""
            SELECT t.*, s.status, s.is_favorite, s.rating, s.reported_watched,
                   0 AS episodes_watched, NULL AS last_watched_at
            FROM titles t
            LEFT JOIN title_state s ON s.title_id = t.id
            WHERE t.enriched_at IS NULL
            ORDER BY t.name
            {"LIMIT " + str(int(limit)) if limit else ""}
            """
        ).fetchall()
        return [_title_row(row) for row in rows]

    # -------------------------------------------------------------- internal

    def _find_title_id(self, title: Title) -> int | None:
        lookups: Sequence[tuple[str, tuple]] = (
            ("SELECT id FROM titles WHERE kind = ? AND tmdb_id = ?", (str(title.kind), title.tmdb_id)),
            ("SELECT id FROM titles WHERE kind = ? AND tvdb_id = ?", (str(title.kind), title.tvdb_id)),
            (
                "SELECT id FROM titles WHERE kind = ? AND name = ? AND year IS ?",
                (str(title.kind), title.name, title.year),
            ),
        )
        for sql, params in lookups:
            if params[1] is None:
                continue
            row = self.conn.execute(sql, params).fetchone()
            if row:
                return int(row["id"])
        return None


def _title_params(title: Title) -> dict:
    return {
        "kind": str(title.kind),
        "name": title.name,
        "year": title.year,
        "tmdb_id": title.tmdb_id,
        "tvdb_id": title.tvdb_id,
        "imdb_id": title.imdb_id,
        "overview": title.overview,
        "poster_path": title.poster_path,
        "backdrop_path": title.backdrop_path,
        "air_status": title.air_status,
        "first_air_date": title.first_air_date,
        "last_air_date": title.last_air_date,
        "total_episodes": title.total_episodes,
        "runtime": title.runtime,
    }


def _title_row(row: sqlite3.Row) -> TitleRow:
    return TitleRow(
        id=row["id"],
        kind=Kind(row["kind"]),
        name=row["name"],
        year=row["year"],
        tmdb_id=row["tmdb_id"],
        tvdb_id=row["tvdb_id"],
        poster_path=row["poster_path"],
        air_status=row["air_status"],
        total_episodes=row["total_episodes"],
        status=Status(row["status"]) if row["status"] else None,
        is_favorite=bool(row["is_favorite"]),
        rating=row["rating"],
        reported_watched=row["reported_watched"],
        episodes_watched=row["episodes_watched"] or 0,
        last_watched_at=row["last_watched_at"],
    )
