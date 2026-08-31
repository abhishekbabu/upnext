"""The SQLite repository behind the `WatchLibrary` port.

Speaks `domain.models` in both directions: nothing above this module handles a
`sqlite3.Row`, and nothing in it decides policy.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence

from upnext.domain.models import (
    Episode,
    EpisodeRow,
    Kind,
    Status,
    Title,
    TitleRow,
    TitleState,
    UnmatchedWatch,
    Watch,
)

# The columns of `titles` that enrichment is allowed to overwrite. `name` and
# `year` are not among them by default: an import names a title from the user's
# own history, and a bad TMDB match should not silently rewrite the library.
# A season number at or above this is a calendar year, not an index. Television
# has not run to a nineteen-hundredth season of anything, so there is nothing to
# be ambiguous about.
SEASON_IS_A_YEAR = 1900

# The columns of `titles` that enrichment is allowed to overwrite. `name` and
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
        """Insert or update one episode of the catalog's list, returning its id.

        Only enrichment reaches here. An import has no idea what a show's
        episodes are — it has a season and a number the exporting service used,
        and that goes on the watch.
        """
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
        """Record one viewing, in the source's own vocabulary.

        No episode row is created and none is looked up. The export knows a
        season and a number the exporting service used; whether the catalog
        agrees is not knowable offline and is not this method's business.
        `link_watches` joins the two once enrichment has an episode list.
        """
        if self._already_recorded(title_id, watch):
            return

        season, number = watch.episode if watch.episode is not None else (None, None)
        self.conn.execute(
            """
            INSERT INTO watches (title_id, watched_at, is_rewatch, source,
                                 source_episode_id, source_season, source_episode)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                title_id,
                watch.watched_at,
                int(watch.is_rewatch),
                watch.source,
                watch.source_episode_id,
                season,
                number,
            ),
        )

    def _already_recorded(self, title_id: int, watch: Watch) -> bool:
        """Whether this exact viewing is in the library already.

        Identity is the source's own episode id where there is one, and the
        source's numbering plus the timestamp where there is not. The second
        form is why a bulk "mark season watched" — one timestamp across fifty
        episodes — does not collapse into a single row, and the first is why
        fifty watches the source declined to number do not either.

        On the source's numbering rather than on a resolved episode, because a
        re-import must converge whether or not enrichment has run since.
        """
        if watch.source_episode_id is not None:
            sql = """
                SELECT 1 FROM watches
                WHERE title_id = ? AND source = ? AND source_episode_id = ? AND watched_at = ?
            """
            params: tuple = (title_id, watch.source, watch.source_episode_id, watch.watched_at)
        else:
            season, number = watch.episode if watch.episode is not None else (None, None)
            sql = """
                SELECT 1 FROM watches
                WHERE title_id = ? AND source = ? AND watched_at = ?
                  AND source_season IS ? AND source_episode IS ? AND source_episode_id IS NULL
            """
            params = (title_id, watch.source, watch.watched_at, season, number)
        return self.conn.execute(sql, params).fetchone() is not None

    def link_watches(self, title_id: int) -> int:
        """Match this title's watches to the catalog episodes they name.

        Run after enrichment has written the episode list. Two passes, and the
        difference between them is the whole design:

        Episode numbers are matched exactly and never approximately. Deciding
        that a viewing of S06E25 was "probably" S06E24 would put a guess into
        the one table that is supposed to be the truth, and Friends' eight
        split finales are exactly that case.

        Season *labels* are a different question, because a label is not a
        claim about content. TheTVDB labels some shows' seasons by calendar
        year where TMDB numbers them 1..N — Sidemen Sundays is 2019 at one and
        season 4 at the other, with identical episode numbering inside. That is
        resolvable from the catalog's own air dates rather than guessed at, so
        the second pass does it: a source season that is plainly a year, not an
        index, is aliased to the catalog season that aired in it.

        The third handles a catalog that keeps a show in one flat run where the
        source split it into seasons — and only when the two can be shown to
        describe the same episodes. See `_link_by_flattened_season`.

        Returns how many watches found an episode.
        """
        return (
            self._link_by_season_number(title_id)
            + self._link_by_season_year(title_id)
            + self._link_by_flattened_season(title_id)
        )

    def _link_by_season_number(self, title_id: int) -> int:
        """The ordinary case: both sides number the season the same way."""
        cursor = self.conn.execute(
            """
            UPDATE watches
               SET episode_id = (
                   SELECT e.id FROM episodes e
                    WHERE e.title_id = watches.title_id
                      AND e.season_number = watches.source_season
                      AND e.episode_number = watches.source_episode
               )
             WHERE title_id = :title_id
               AND episode_id IS NULL
               AND source_season IS NOT NULL
               AND EXISTS (
                   SELECT 1 FROM episodes e
                    WHERE e.title_id = watches.title_id
                      AND e.season_number = watches.source_season
                      AND e.episode_number = watches.source_episode
               )
            """,
            {"title_id": title_id},
        )
        return cursor.rowcount

    def _link_by_flattened_season(self, title_id: int) -> int:
        """The source split a run the catalog keeps flat.

        TMDB lists Yu-Gi-Oh! Duel Monsters as one season of 224 episodes;
        TheTVDB splits the same 224 into five. Nothing about a season number
        can bridge that, but the two orderings can still be laid side by side —
        if, and only if, they are the same length and provably in step.

        Three conditions, all of which must hold:

        1. The catalog has exactly one numbered season. Anything else and the
           two are not disagreeing about grouping, they are disagreeing about
           content, and this has nothing to say.
        2. The source names exactly as many distinct episodes as that season
           holds. A partially watched show cannot satisfy this, which is the
           point: without a complete run there is no way to know how long the
           source's seasons were, and the offsets would be invented.
        3. Every watch that already matched by number agrees with the ordering.
           This is the load-bearing one — it makes the mapping a hypothesis the
           existing matches confirm, rather than an assumption. For Duel
           Monsters the first forty-nine already match one-to-one, and they go
           on matching under the ordinal reading; if they did not, the reading
           would be wrong and nothing is written.
        """
        seasons = self.conn.execute(
            "SELECT DISTINCT season_number FROM episodes WHERE title_id = ? AND season_number > 0",
            (title_id,),
        ).fetchall()
        if len(seasons) != 1:
            return 0

        catalog = self.conn.execute(
            """
            SELECT id, season_number, episode_number FROM episodes
             WHERE title_id = ? AND season_number > 0
             ORDER BY season_number, episode_number
            """,
            (title_id,),
        ).fetchall()
        source = self.conn.execute(
            """
            SELECT DISTINCT source_season, source_episode FROM watches
             WHERE title_id = ? AND source_season > 0
             ORDER BY source_season, source_episode
            """,
            (title_id,),
        ).fetchall()
        if not catalog or len(catalog) != len(source):
            return 0

        pairs = list(zip(catalog, source, strict=True))
        if not self._ordering_agrees_with_what_matched(title_id, pairs):
            return 0

        updated = 0
        for episode, watched in pairs:
            cursor = self.conn.execute(
                """
                UPDATE watches SET episode_id = :episode_id
                 WHERE title_id = :title_id AND episode_id IS NULL
                   AND source_season = :season AND source_episode = :number
                """,
                {
                    "episode_id": episode["id"],
                    "title_id": title_id,
                    "season": watched["source_season"],
                    "number": watched["source_episode"],
                },
            )
            updated += cursor.rowcount
        return updated

    def _ordering_agrees_with_what_matched(self, title_id: int, pairs: Sequence[tuple]) -> bool:
        """Whether every already-matched watch lands where the ordering says.

        The exact-number pass has run by now, so these are matches made on
        evidence. If the ordinal reading disagrees with even one of them, it is
        describing a different show than the numbers are.
        """
        matched = {
            (row["source_season"], row["source_episode"]): row["episode_id"]
            for row in self.conn.execute(
                """
                SELECT DISTINCT source_season, source_episode, episode_id FROM watches
                 WHERE title_id = ? AND episode_id IS NOT NULL AND source_season > 0
                """,
                (title_id,),
            )
        }
        if not matched:
            return False

        for episode, watched in pairs:
            key = (watched["source_season"], watched["source_episode"])
            if key in matched and matched[key] != episode["id"]:
                return False
        return True

    def _link_by_season_year(self, title_id: int) -> int:
        """The aliased case: the source labelled the season with its year.

        A season number at or above `SEASON_IS_A_YEAR` cannot be an index —
        no show has a nineteen-hundredth season — so reading it as a year is
        not a guess. The catalog season it refers to is the one that actually
        aired that year, taken by weight of episodes so that a season
        straddling New Year resolves to the year most of it belongs to.
        """
        cursor = self.conn.execute(
            """
            UPDATE watches
               SET episode_id = (
                   SELECT e.id FROM episodes e
                    WHERE e.title_id = watches.title_id
                      AND e.episode_number = watches.source_episode
                      AND e.season_number = (
                          SELECT e2.season_number FROM episodes e2
                           WHERE e2.title_id = watches.title_id
                             AND substr(e2.air_date, 1, 4) = CAST(watches.source_season AS TEXT)
                           GROUP BY e2.season_number
                           ORDER BY COUNT(*) DESC, e2.season_number
                           LIMIT 1
                      )
               )
             WHERE title_id = :title_id
               AND episode_id IS NULL
               AND source_season >= :year_floor
               AND EXISTS (
                   SELECT 1 FROM episodes e
                    WHERE e.title_id = watches.title_id
                      AND e.episode_number = watches.source_episode
                      AND e.season_number = (
                          SELECT e2.season_number FROM episodes e2
                           WHERE e2.title_id = watches.title_id
                             AND substr(e2.air_date, 1, 4) = CAST(watches.source_season AS TEXT)
                           GROUP BY e2.season_number
                           ORDER BY COUNT(*) DESC, e2.season_number
                           LIMIT 1
                      )
               )
            """,
            {"title_id": title_id, "year_floor": SEASON_IS_A_YEAR},
        )
        return cursor.rowcount

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
                   COUNT(DISTINCT CASE WHEN e.season_number > 0 THEN w.episode_id END) AS episodes_watched,
                   COUNT(DISTINCT CASE WHEN w.episode_id IS NULL AND w.source_season > 0
                                       THEN w.source_season || 'x' || w.source_episode END) AS unmatched_watched,
                   MAX(w.watched_at) AS last_watched_at
            FROM titles t
            LEFT JOIN title_state s ON s.title_id = t.id
            LEFT JOIN watches w ON w.title_id = t.id
            -- Only to read the season off a watch. LEFT so a watch the export
            -- could not number keeps its row and its timestamp.
            LEFT JOIN episodes e ON e.id = w.episode_id
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
                   COUNT(DISTINCT CASE WHEN e.season_number > 0 THEN w.episode_id END) AS episodes_watched,
                   COUNT(DISTINCT CASE WHEN w.episode_id IS NULL AND w.source_season > 0
                                       THEN w.source_season || 'x' || w.source_episode END) AS unmatched_watched,
                   MAX(w.watched_at) AS last_watched_at
            FROM titles t
            LEFT JOIN title_state s ON s.title_id = t.id
            LEFT JOIN watches w ON w.title_id = t.id
            -- Only to read the season off a watch. LEFT so a watch the export
            -- could not number keeps its row and its timestamp.
            LEFT JOIN episodes e ON e.id = w.episode_id
            WHERE t.id = ?
            GROUP BY t.id
            """,
            (title_id,),
        ).fetchone()
        return _title_row(row) if row else None

    def episodes(self, title_id: int) -> list[EpisodeRow]:
        """Every episode of a title, in order, with how often it was watched."""
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
        return [_episode_row(row) for row in rows]

    def unmatched_watches(self, title_id: int) -> list[UnmatchedWatch]:
        """Viewings this title's catalog episode list does not account for.

        Grouped by what the source called the episode, so a rewatch is one row
        with a count rather than two rows. Ordered by the source's numbering,
        which is the order they were watched in for anyone who watched in order.
        """
        rows = self.conn.execute(
            """
            SELECT source_season, source_episode,
                   COUNT(*) AS watch_count, MAX(watched_at) AS last_watched_at
            FROM watches
            WHERE title_id = ? AND episode_id IS NULL AND source_season IS NOT NULL
            GROUP BY source_season, source_episode
            ORDER BY source_season, source_episode
            """,
            (title_id,),
        ).fetchall()
        return [
            UnmatchedWatch(
                season_number=row["source_season"],
                episode_number=row["source_episode"],
                watch_count=row["watch_count"],
                last_watched_at=row["last_watched_at"],
            )
            for row in rows
        ]

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
                   -- An episode is one episode whether the catalog lists it or
                   -- not: a matched one counts by its id, an unmatched one by
                   -- what the source called it. A watch the export declined to
                   -- number counts as neither, which is why Beyblade's viewing
                   -- total is honest and its episode total is short.
                   COUNT(DISTINCT CASE
                       WHEN episode_id IS NOT NULL THEN 'e' || episode_id
                       WHEN source_season IS NOT NULL
                           THEN 'u' || title_id || 'x' || source_season || 'x' || source_episode
                   END) AS episodes,
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

    def title_by_tmdb_id(self, tmdb_id: int) -> TitleRow | None:
        row = self.conn.execute(
            "SELECT id FROM titles WHERE kind = ? AND tmdb_id = ?", (str(Kind.SHOW), tmdb_id)
        ).fetchone()
        return self.title(int(row["id"])) if row else None

    def move_watches(self, *, source_id: int, target_id: int, season: int, as_season: int) -> int:
        """Reassign one source season's viewings to a different title.

        For where the export and the catalog disagree about what counts as one
        show: TV Time files The Haunting of Bly Manor as season 2 of The
        Haunting, and TMDB keeps it as its own title. The viewings are right;
        the show they were filed under is not.

        `episode_id` is cleared because the target's episode list is a
        different list — whatever these matched before means nothing here, and
        `link_watches` decides again from scratch.
        """
        cursor = self.conn.execute(
            """
            UPDATE watches
               SET title_id = :target_id, source_season = :as_season, episode_id = NULL
             WHERE title_id = :source_id AND source_season = :season
            """,
            {"target_id": target_id, "source_id": source_id, "season": season, "as_season": as_season},
        )
        return cursor.rowcount

    def count_titles(self) -> int:
        """How many titles the library holds at all, enriched or not."""
        return int(self.conn.execute("SELECT COUNT(*) AS n FROM titles").fetchone()["n"])

    def needing_enrichment(self, *, limit: int | None = None) -> list[TitleRow]:
        rows = self.conn.execute(
            f"""
            SELECT t.*, s.status, s.is_favorite, s.rating, s.reported_watched,
                   0 AS episodes_watched, 0 AS unmatched_watched, NULL AS last_watched_at
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
        imdb_id=row["imdb_id"],
        overview=row["overview"],
        poster_path=row["poster_path"],
        backdrop_path=row["backdrop_path"],
        air_status=row["air_status"],
        first_air_date=row["first_air_date"],
        last_air_date=row["last_air_date"],
        total_episodes=row["total_episodes"],
        runtime=row["runtime"],
        status=Status(row["status"]) if row["status"] else None,
        is_favorite=bool(row["is_favorite"]),
        rating=row["rating"],
        reported_watched=row["reported_watched"],
        episodes_watched=row["episodes_watched"] or 0,
        unmatched_watched=row["unmatched_watched"] or 0,
        enriched_at=row["enriched_at"],
        last_watched_at=row["last_watched_at"],
    )


def _episode_row(row: sqlite3.Row) -> EpisodeRow:
    return EpisodeRow(
        id=row["id"],
        season_number=row["season_number"],
        episode_number=row["episode_number"],
        name=row["name"],
        overview=row["overview"],
        air_date=row["air_date"],
        runtime=row["runtime"],
        still_path=row["still_path"],
        watch_count=row["watch_count"] or 0,
        last_watched_at=row["last_watched_at"],
    )
