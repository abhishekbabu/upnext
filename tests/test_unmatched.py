"""Viewings the catalog's episode list cannot account for.

TMDB is the source of truth for what a show *is*. The export is the source of
truth for what was *watched*. They do not always agree about how a show is
divided up, and this is where that meets the ground:

  Friends           TheTVDB splits eight double-length episodes TMDB counts once
  The Haunting      TV Time files Bly Manor as season 2 of a title TMDB ends at 1
  Sidemen Sundays   seasons labelled 2019 at one and 4 at the other

Only the first two are real disagreements. The third is a label, and a label
is resolvable — see the year-alias tests at the foot of this file. Every
viewing in all three is real, and none of them should invent an episode.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from upnext.adapters.outbound.store.db import connect, migrate
from upnext.adapters.outbound.store.library import Library
from upnext.application.enrichment import move_season
from upnext.domain.models import Episode, Status, Title, TitleState, Watch
from upnext.domain.ports import CatalogShow

ENRICHED = "2026-08-31T00:00:00+00:00"


def a_show(library: Library, name: str = "Friends") -> int:
    title_id = library.upsert_title(Title(name=name, tvdb_id=79168))
    library.set_state(title_id, TitleState(status=Status.WATCHING))
    return title_id


def enrich(library: Library, title_id: int, *, total: int, episodes: list[tuple[int, int]]) -> None:
    """Stand in for a catalog answering, without one."""
    library.apply_enrichment(title_id, Title(name="Friends", tvdb_id=79168, total_episodes=total), enriched_at=ENRICHED)
    for season, number in episodes:
        library.upsert_episode(title_id, Episode(season_number=season, episode_number=number))
    library.link_watches(title_id)


# ── an import writes no episodes ────────────────────────────────────────


def test_recording_a_watch_invents_no_episode(library: Library) -> None:
    """The export knows a number. It does not know the show's structure."""
    title_id = a_show(library)
    library.record_watch(title_id, Watch(watched_at="2018-05-12 01:10:14", episode=(1, 1)))

    assert library.episodes(title_id) == []
    # The viewing is kept whole, in the source's own words.
    assert library.unmatched_watches(title_id)[0].season_number == 1
    assert library.stats()["watches"] == 1


def test_an_unenriched_title_counts_its_watches_but_measures_no_progress(library: Library) -> None:
    title_id = a_show(library)
    for number in (1, 2, 3):
        library.record_watch(title_id, Watch(watched_at=f"2018-05-{number:02d} 00:00:00", episode=(1, number)))

    row = library.title(title_id)
    assert row.enriched_at is None
    assert (row.episodes_watched, row.unmatched_watched, row.total_episodes) == (0, 3, None)


# ── enrichment joins the two ────────────────────────────────────────────


def test_enrichment_matches_the_watches_that_were_waiting(library: Library) -> None:
    title_id = a_show(library)
    for number in (1, 2):
        library.record_watch(title_id, Watch(watched_at=f"2018-05-{number:02d} 00:00:00", episode=(1, number)))

    enrich(library, title_id, total=2, episodes=[(1, 1), (1, 2)])

    row = library.title(title_id)
    assert (row.episodes_watched, row.unmatched_watched) == (2, 0)
    assert [(e.season_number, e.episode_number, e.watch_count) for e in library.episodes(title_id)] == [
        (1, 1, 1),
        (1, 2, 1),
    ]


def test_a_watch_the_catalog_has_no_episode_for_stays_unmatched(library: Library) -> None:
    """The Friends shape: a complete watch against a shorter list."""
    title_id = a_show(library)
    for number in (1, 2, 3):
        library.record_watch(title_id, Watch(watched_at=f"2018-05-{number:02d} 00:00:00", episode=(1, number)))

    # The catalog folds the third into the second.
    enrich(library, title_id, total=2, episodes=[(1, 1), (1, 2)])

    row = library.title(title_id)
    assert (row.episodes_watched, row.unmatched_watched, row.total_episodes) == (2, 1, 2)
    # Matched progress is complete, and the extra viewing is still on the record.
    unmatched = library.unmatched_watches(title_id)
    assert [(u.season_number, u.episode_number, u.watch_count) for u in unmatched] == [(1, 3, 1)]


def test_a_year_labelled_season_the_catalog_cannot_place_loses_nothing(library: Library) -> None:
    """A year label with no air dates to resolve it against.

    The alias needs the catalog to say when a season aired; without that there
    is nothing to resolve and the viewings stay unmatched — kept, not guessed.
    """
    title_id = a_show(library, "Sidemen Sundays")
    for number in (28, 33):
        library.record_watch(title_id, Watch(watched_at=f"2018-07-{number - 20:02d} 00:00:00", episode=(2018, number)))

    enrich(library, title_id, total=3, episodes=[(1, 1), (1, 2), (1, 3)])

    row = library.title(title_id)
    assert (row.episodes_watched, row.unmatched_watched) == (0, 2)
    # The catalog's list is intact and is the only thing in `episodes`.
    assert len(library.episodes(title_id)) == 3
    assert [(u.season_number, u.episode_number) for u in library.unmatched_watches(title_id)] == [
        (2018, 28),
        (2018, 33),
    ]


def test_matching_is_exact_and_never_guesses(library: Library) -> None:
    """S06E25 is not "probably" S06E24.

    A near-miss written into `episodes` would be an invention in the one table
    that is supposed to be the catalog's.
    """
    title_id = a_show(library)
    library.record_watch(title_id, Watch(watched_at="2018-05-01 00:00:00", episode=(6, 25)))

    enrich(library, title_id, total=24, episodes=[(6, number) for number in range(1, 25)])

    assert library.title(title_id).unmatched_watched == 1
    assert library.unmatched_watches(title_id)[0].episode_number == 25


def test_a_second_enrichment_picks_up_what_the_catalog_has_since_added(library: Library) -> None:
    title_id = a_show(library)
    library.record_watch(title_id, Watch(watched_at="2018-05-01 00:00:00", episode=(2, 1)))
    enrich(library, title_id, total=1, episodes=[(1, 1)])
    assert library.title(title_id).unmatched_watched == 1

    enrich(library, title_id, total=2, episodes=[(1, 1), (2, 1)])
    assert (library.title(title_id).episodes_watched, library.title(title_id).unmatched_watched) == (1, 0)


# ── counting ────────────────────────────────────────────────────────────


def test_a_rewatch_is_one_episode_and_two_viewings(library: Library) -> None:
    title_id = a_show(library)
    library.record_watch(title_id, Watch(watched_at="2018-05-12 01:10:14", episode=(1, 1)))
    library.record_watch(title_id, Watch(watched_at="2021-04-23 00:23:28", episode=(1, 1)))

    enrich(library, title_id, total=1, episodes=[(1, 1)])

    assert library.title(title_id).episodes_watched == 1
    assert library.stats()["watches"] == 2
    assert library.episodes(title_id)[0].watch_count == 2


def test_an_unmatched_rewatch_is_one_episode_too(library: Library) -> None:
    title_id = a_show(library)
    for watched_at in ("2018-05-12 01:10:14", "2021-04-23 00:23:28"):
        library.record_watch(title_id, Watch(watched_at=watched_at, episode=(9, 9)))

    enrich(library, title_id, total=1, episodes=[(1, 1)])

    assert library.title(title_id).unmatched_watched == 1
    assert library.unmatched_watches(title_id)[0].watch_count == 2


def test_specials_are_neither_progress_nor_a_disagreement(library: Library) -> None:
    """Season 0 is out of the catalog's total, so it is out of both counts."""
    title_id = a_show(library, "INVINCIBLE")
    library.record_watch(title_id, Watch(watched_at="2024-01-01 00:00:00", episode=(1, 1)))
    library.record_watch(title_id, Watch(watched_at="2024-02-01 00:00:00", episode=(0, 1)))

    enrich(library, title_id, total=1, episodes=[(1, 1), (0, 1)])

    row = library.title(title_id)
    assert (row.episodes_watched, row.unmatched_watched, row.total_episodes) == (1, 0, 1)
    # Still stored, still shown, still a viewing.
    assert len(library.episodes(title_id)) == 2
    assert library.stats()["episodes_watched"] == 2


def test_the_library_wide_total_counts_an_episode_once_either_way(library: Library) -> None:
    title_id = a_show(library)
    library.record_watch(title_id, Watch(watched_at="2018-05-01 00:00:00", episode=(1, 1)))
    library.record_watch(title_id, Watch(watched_at="2018-05-02 00:00:00", episode=(9, 9)))

    enrich(library, title_id, total=1, episodes=[(1, 1)])

    assert library.stats()["episodes_watched"] == 2


def test_a_watch_the_export_could_not_number_counts_as_viewing_only(library: Library) -> None:
    """The Beyblade case, unchanged by any of this."""
    title_id = a_show(library, "Beyblade")
    library.record_watch(title_id, Watch(watched_at="2017-03-07 05:27:58", episode=None))

    row = library.title(title_id)
    assert (row.episodes_watched, row.unmatched_watched) == (0, 0)
    assert row.last_watched_at == "2017-03-07 05:27:58"
    assert library.stats()["watches"] == 1
    assert library.stats()["episodes_watched"] == 0
    assert library.unmatched_watches(title_id) == []


def test_the_list_and_the_detail_agree(library: Library) -> None:
    title_id = a_show(library)
    library.record_watch(title_id, Watch(watched_at="2018-05-01 00:00:00", episode=(1, 1)))
    library.record_watch(title_id, Watch(watched_at="2018-05-02 00:00:00", episode=(1, 9)))
    enrich(library, title_id, total=1, episodes=[(1, 1)])

    listed, one = library.titles()[0], library.title(title_id)
    assert (listed.episodes_watched, listed.unmatched_watched) == (1, 1)
    assert (one.episodes_watched, one.unmatched_watched) == (1, 1)


# ── idempotence ─────────────────────────────────────────────────────────


def test_the_same_watch_imported_twice_is_stored_once(library: Library) -> None:
    title_id = a_show(library)
    for _ in range(2):
        library.record_watch(
            title_id,
            Watch(watched_at="2018-05-12 01:10:14", episode=(1, 1), source="tvtime", source_episode_id="303821"),
        )
    assert library.stats()["watches"] == 1


def test_a_re_import_after_enrichment_still_converges(library: Library) -> None:
    """Identity is the source's numbering, which does not change when a watch
    gains an episode_id — so a second import must not duplicate it."""
    title_id = a_show(library)
    watch = Watch(watched_at="2018-05-12 01:10:14", episode=(1, 1), source="tvtime")
    library.record_watch(title_id, watch)
    enrich(library, title_id, total=1, episodes=[(1, 1)])

    library.record_watch(title_id, watch)
    assert library.stats()["watches"] == 1


def test_two_unnumbered_watches_at_the_same_second_are_two_rows(library: Library) -> None:
    """TV Time can issue two distinct episodes with one timestamp."""
    title_id = a_show(library)
    library.record_watch(title_id, Watch(watched_at="2020-01-02 03:04:05", episode=(3, 13), source="tvtime"))
    library.record_watch(title_id, Watch(watched_at="2020-01-02 03:04:05", episode=(3, 14), source="tvtime"))
    assert library.stats()["watches"] == 2


# ── migration ───────────────────────────────────────────────────────────


def test_an_existing_library_is_reshaped_without_a_re_import(tmp_path: Path) -> None:
    """`CREATE TABLE IF NOT EXISTS` never alters a table that already exists.

    An enrichment run is hundreds of API calls, so a library someone already
    has moves to the new shape in place.
    """
    db_path = tmp_path / "old.db"
    old = sqlite3.connect(db_path)
    old.row_factory = sqlite3.Row
    old.executescript(
        """
        CREATE TABLE titles (id INTEGER PRIMARY KEY, name TEXT, enriched_at TEXT);
        CREATE TABLE episodes (
            id INTEGER PRIMARY KEY, title_id INTEGER, season_number INTEGER,
            episode_number INTEGER, tmdb_id INTEGER
        );
        CREATE TABLE watches (
            id INTEGER PRIMARY KEY, title_id INTEGER, episode_id INTEGER,
            watched_at TEXT, is_rewatch INTEGER DEFAULT 0,
            source_episode_id TEXT, source TEXT DEFAULT 'upnext'
        );
        CREATE UNIQUE INDEX watches_episode_time
            ON watches (title_id, episode_id, watched_at, source)
            WHERE source_episode_id IS NULL AND episode_id IS NOT NULL;

        INSERT INTO titles (id, name, enriched_at) VALUES (1, 'Friends', '2026-01-01T00:00:00+00:00');
        -- One TMDB gave us, one the old import invented.
        INSERT INTO episodes (id, title_id, season_number, episode_number, tmdb_id) VALUES (10, 1, 1, 1, 500);
        INSERT INTO episodes (id, title_id, season_number, episode_number, tmdb_id) VALUES (11, 1, 6, 25, NULL);
        INSERT INTO watches (title_id, episode_id, watched_at) VALUES (1, 10, '2018-05-12 01:10:14');
        INSERT INTO watches (title_id, episode_id, watched_at) VALUES (1, 11, '2018-06-01 00:00:00');
        """
    )
    old.commit()

    migrate(old)

    # Both viewings survive. The invented row does not.
    assert old.execute("SELECT COUNT(*) n FROM watches").fetchone()["n"] == 2
    assert old.execute("SELECT COUNT(*) n FROM episodes").fetchone()["n"] == 1

    rows = old.execute("SELECT episode_id, source_season, source_episode FROM watches ORDER BY id").fetchall()
    # The matched one keeps its episode and gains the numbering it came from.
    assert (rows[0]["episode_id"], rows[0]["source_season"], rows[0]["source_episode"]) == (10, 1, 1)
    # The other keeps the numbering and lets go of the invented episode.
    assert (rows[1]["episode_id"], rows[1]["source_season"], rows[1]["source_episode"]) == (None, 6, 25)
    old.close()


def test_migrating_twice_changes_nothing(tmp_path: Path) -> None:
    """It runs on every connect, so it has to be safe to run on every connect."""
    db_path = tmp_path / "library.db"
    conn = connect(db_path)
    library = Library(conn)
    title_id = a_show(library)
    library.record_watch(title_id, Watch(watched_at="2018-05-12 01:10:14", episode=(1, 1)))
    enrich(library, title_id, total=1, episodes=[(1, 1)])
    conn.commit()
    conn.close()

    again = connect(db_path)
    row = Library(again).title(title_id)
    assert (row.episodes_watched, row.unmatched_watched) == (1, 0)
    again.close()


# ── seasons the source labelled with a year ─────────────────────────────


def test_a_year_labelled_season_is_aliased_to_the_one_that_aired_then(library: Library) -> None:
    """Sidemen Sundays: TheTVDB says season 2019, TMDB says season 4.

    Identical episode numbering inside, and the catalog's own air dates say
    which season 2019 was — so this is a label resolved, not an episode guessed.
    """
    title_id = a_show(library, "Sidemen Sundays")
    for number in (1, 2, 3):
        library.record_watch(title_id, Watch(watched_at=f"2019-01-{number:02d} 00:00:00", episode=(2019, number)))

    library.apply_enrichment(
        title_id, Title(name="Sidemen Sundays", tvdb_id=79168, total_episodes=6), enriched_at=ENRICHED
    )
    for number in (1, 2, 3):
        library.upsert_episode(
            title_id, Episode(season_number=3, episode_number=number, air_date=f"2018-01-{number:02d}")
        )
        library.upsert_episode(
            title_id, Episode(season_number=4, episode_number=number, air_date=f"2019-01-{number:02d}")
        )
    library.link_watches(title_id)

    row = library.title(title_id)
    assert (row.episodes_watched, row.unmatched_watched) == (3, 0)
    # Matched into season 4, which is the one that aired in 2019.
    assert [e.watch_count for e in library.episodes(title_id) if e.season_number == 4] == [1, 1, 1]
    assert [e.watch_count for e in library.episodes(title_id) if e.season_number == 3] == [0, 0, 0]


def test_an_ordinary_season_number_is_never_read_as_a_year(library: Library) -> None:
    """The alias applies only to numbers that cannot be an index at all."""
    title_id = a_show(library)
    library.record_watch(title_id, Watch(watched_at="2019-01-01 00:00:00", episode=(3, 1)))

    library.apply_enrichment(title_id, Title(name="Friends", tvdb_id=79168, total_episodes=1), enriched_at=ENRICHED)
    library.upsert_episode(title_id, Episode(season_number=4, episode_number=1, air_date="2019-01-01"))
    library.link_watches(title_id)

    # Season 3 does not exist in the catalog, and 3 is not a year, so no alias.
    assert library.title(title_id).unmatched_watched == 1


def test_a_year_with_no_season_behind_it_stays_unmatched(library: Library) -> None:
    title_id = a_show(library, "Sidemen Sundays")
    library.record_watch(title_id, Watch(watched_at="2019-01-01 00:00:00", episode=(2031, 1)))

    library.apply_enrichment(
        title_id, Title(name="Sidemen Sundays", tvdb_id=79168, total_episodes=1), enriched_at=ENRICHED
    )
    library.upsert_episode(title_id, Episode(season_number=1, episode_number=1, air_date="2019-01-01"))
    library.link_watches(title_id)

    assert library.title(title_id).unmatched_watched == 1


def test_the_alias_still_matches_the_episode_number_exactly(library: Library) -> None:
    """Resolving which season is not licence to guess which episode."""
    title_id = a_show(library, "Sidemen Sundays")
    library.record_watch(title_id, Watch(watched_at="2019-01-01 00:00:00", episode=(2019, 99)))

    library.apply_enrichment(
        title_id, Title(name="Sidemen Sundays", tvdb_id=79168, total_episodes=1), enriched_at=ENRICHED
    )
    library.upsert_episode(title_id, Episode(season_number=4, episode_number=1, air_date="2019-01-01"))
    library.link_watches(title_id)

    assert library.title(title_id).unmatched_watched == 1


def test_a_season_straddling_new_year_resolves_to_where_most_of_it_aired(library: Library) -> None:
    title_id = a_show(library, "Sidemen Sundays")
    library.record_watch(title_id, Watch(watched_at="2019-06-01 00:00:00", episode=(2019, 2)))

    library.apply_enrichment(
        title_id, Title(name="Sidemen Sundays", tvdb_id=79168, total_episodes=4), enriched_at=ENRICHED
    )
    # Season 3 ends with one episode in January 2019; season 4 is all of it.
    library.upsert_episode(title_id, Episode(season_number=3, episode_number=2, air_date="2019-01-05"))
    library.upsert_episode(title_id, Episode(season_number=4, episode_number=1, air_date="2019-03-01"))
    library.upsert_episode(title_id, Episode(season_number=4, episode_number=2, air_date="2019-06-01"))
    library.upsert_episode(title_id, Episode(season_number=4, episode_number=3, air_date="2019-09-01"))
    library.link_watches(title_id)

    matched = [e for e in library.episodes(title_id) if e.watch_count > 0]
    assert [(e.season_number, e.episode_number) for e in matched] == [(4, 2)]


# ── a run the catalog keeps flat ────────────────────────────────────────


def flat_show(library: Library, *, catalog: int, watched: list[tuple[int, int]]) -> int:
    """A catalog holding one season of `catalog` episodes, against a split source."""
    title_id = a_show(library, "Yu-Gi-Oh! Duel Monsters")
    for season, number in watched:
        library.record_watch(title_id, Watch(watched_at=f"2019-01-01 00:00:{number:02d}", episode=(season, number)))
    library.apply_enrichment(
        title_id,
        Title(name="Yu-Gi-Oh! Duel Monsters", tvdb_id=79168, total_episodes=catalog),
        enriched_at=ENRICHED,
    )
    for number in range(1, catalog + 1):
        library.upsert_episode(title_id, Episode(season_number=1, episode_number=number))
    library.link_watches(title_id)
    return title_id


def test_a_split_run_maps_onto_a_flat_one_when_the_two_are_the_same_length(library: Library) -> None:
    """TMDB has Duel Monsters as one season of 224; TheTVDB splits it into five.

    In miniature: the source's 1x1,1x2,2x1,2x2 is the catalog's 1..4.
    """
    title_id = flat_show(library, catalog=4, watched=[(1, 1), (1, 2), (2, 1), (2, 2)])

    row = library.title(title_id)
    assert (row.episodes_watched, row.unmatched_watched) == (4, 0)
    assert [e.watch_count for e in library.episodes(title_id)] == [1, 1, 1, 1]


def test_a_partly_watched_split_run_is_left_alone(library: Library) -> None:
    """Without a complete run there is no way to know how long a source season
    was, so the offsets would be invented. Yu-Gi-Oh! 5D's is this case: 78
    episodes watched of a catalog 154."""
    title_id = flat_show(library, catalog=6, watched=[(1, 1), (2, 1), (2, 2)])

    row = library.title(title_id)
    # 1x1 still matches by number; the rest are honestly unaccounted for.
    assert (row.episodes_watched, row.unmatched_watched) == (1, 2)


def test_the_ordering_must_agree_with_what_already_matched(library: Library) -> None:
    """The load-bearing guard: existing matches confirm the reading, or veto it.

    Here 1x3 matched by number to the catalog's third episode, but the ordinal
    reading would put it fourth. The two disagree, so nothing is written.
    """
    title_id = flat_show(library, catalog=4, watched=[(1, 1), (1, 3), (2, 1), (2, 2)])

    row = library.title(title_id)
    assert row.unmatched_watched == 2
    assert [(u.season_number, u.episode_number) for u in library.unmatched_watches(title_id)] == [(2, 1), (2, 2)]


def test_a_catalog_with_real_seasons_is_never_flattened(library: Library) -> None:
    """Two seasons at the catalog means the disagreement is about content."""
    title_id = a_show(library)
    library.record_watch(title_id, Watch(watched_at="2019-01-01 00:00:00", episode=(3, 1)))
    library.apply_enrichment(title_id, Title(name="Friends", tvdb_id=79168, total_episodes=2), enriched_at=ENRICHED)
    library.upsert_episode(title_id, Episode(season_number=1, episode_number=1))
    library.upsert_episode(title_id, Episode(season_number=2, episode_number=1))
    library.link_watches(title_id)

    assert library.title(title_id).unmatched_watched == 1


def test_nothing_is_mapped_when_no_watch_matched_by_number_first(library: Library) -> None:
    """With no confirmed match there is nothing to check the ordering against,
    and an unchecked ordering is a guess."""
    title_id = flat_show(library, catalog=2, watched=[(7, 1), (8, 1)])

    assert library.title(title_id).unmatched_watched == 2


# ── a season that belongs to a different title entirely ─────────────────


class OneShowCatalog:
    """A catalog holding a single show, for moving a season into."""

    def __init__(self, name: str, episodes: list[tuple[int, int]], *, tmdb_id: int = 109958) -> None:
        self.show = CatalogShow(
            title=Title(name=name, tmdb_id=tmdb_id, total_episodes=len(episodes)),
            episodes=[Episode(season_number=s, episode_number=n) for s, n in episodes],
        )

    def find_by_tvdb(self, tvdb_id: int):
        return None

    def search_shows(self, name: str, *, year: int | None = None):
        return []

    def fetch_show(self, catalog_id: int) -> CatalogShow:
        return self.show


def test_a_season_moves_to_the_title_the_catalog_keeps_it_under(library: Library) -> None:
    """TV Time files Bly Manor as season 2 of The Haunting; TMDB does not."""
    title_id = a_show(library, "The Haunting")
    library.record_watch(title_id, Watch(watched_at="2018-10-12 00:00:00", episode=(1, 1)))
    for number in (1, 2):
        library.record_watch(title_id, Watch(watched_at=f"2020-10-0{number} 00:00:00", episode=(2, number)))
    enrich(library, title_id, total=1, episodes=[(1, 1)])

    catalog = OneShowCatalog("The Haunting of Bly Manor", [(1, 1), (1, 2)])
    result = move_season(catalog, library, source=library.title(title_id), tmdb_id=109958, season=2, as_season=1)

    assert (result.target, result.moved, result.linked) == ("The Haunting of Bly Manor", 2, 2)
    # The source keeps what was actually its own, and nothing is left over.
    source = library.title(title_id)
    assert (source.episodes_watched, source.unmatched_watched) == (1, 0)
    target = library.title_by_tmdb_id(109958)
    assert (target.episodes_watched, target.unmatched_watched, target.total_episodes) == (2, 0, 2)
    # Every viewing survives the move.
    assert library.stats()["watches"] == 3


def test_a_moved_season_is_renumbered_into_the_target(library: Library) -> None:
    """Whose Line's revival is seasons 9-12 at the export and 1-4 at TMDB."""
    title_id = a_show(library, "Whose Line Is It Anyway? (US)")
    library.record_watch(title_id, Watch(watched_at="2013-07-16 00:00:00", episode=(9, 1)))
    enrich(library, title_id, total=1, episodes=[(1, 1)])

    catalog = OneShowCatalog("Whose Line Is It Anyway?", [(1, 1)], tmdb_id=64978)
    move_season(catalog, library, source=library.title(title_id), tmdb_id=64978, season=9, as_season=1)

    target = library.title_by_tmdb_id(64978)
    assert [(e.season_number, e.episode_number, e.watch_count) for e in library.episodes(target.id)] == [(1, 1, 1)]


def test_the_moved_title_inherits_the_state_it_was_filed_under(library: Library) -> None:
    """The only guess worth making about a title nobody has expressed a view on."""
    title_id = a_show(library, "The Haunting")
    library.set_state(title_id, TitleState(status=Status.COMPLETED))
    library.record_watch(title_id, Watch(watched_at="2020-10-01 00:00:00", episode=(2, 1)))

    catalog = OneShowCatalog("The Haunting of Bly Manor", [(1, 1)])
    move_season(catalog, library, source=library.title(title_id), tmdb_id=109958, season=2, as_season=1)

    assert library.title_by_tmdb_id(109958).status is Status.COMPLETED


def test_moving_into_a_title_the_library_already_has_does_not_duplicate_it(library: Library) -> None:
    existing = library.upsert_title(Title(name="The Haunting of Bly Manor", tmdb_id=109958))
    library.set_state(existing, TitleState(status=Status.WATCHING))

    title_id = a_show(library, "The Haunting")
    library.record_watch(title_id, Watch(watched_at="2020-10-01 00:00:00", episode=(2, 1)))

    catalog = OneShowCatalog("The Haunting of Bly Manor", [(1, 1)])
    move_season(catalog, library, source=library.title(title_id), tmdb_id=109958, season=2, as_season=1)

    assert library.count_titles() == 2
    assert library.title(existing).episodes_watched == 1
