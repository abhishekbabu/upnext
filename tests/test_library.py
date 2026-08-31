from __future__ import annotations

from upnext.importers.tvtime import read_export
from upnext.models import Episode, Kind, Status, Title, TitleState, Watch
from upnext.store.library import Library


def a_show(library: Library, name: str = "Friends", **kwargs) -> int:
    return library.upsert_title(Title(name=name, kind=Kind.SHOW, **kwargs))


def test_a_title_is_matched_by_tvdb_id_not_duplicated(library: Library) -> None:
    first = a_show(library, tvdb_id=79168)
    second = library.upsert_title(Title(name="Friends", kind=Kind.SHOW, tvdb_id=79168, year=1994))
    assert first == second
    assert library.title(first).year == 1994


def test_an_import_never_erases_enriched_columns(library: Library) -> None:
    title_id = a_show(library, tvdb_id=79168)
    library.apply_enrichment(
        title_id,
        Title(name="Friends", tvdb_id=79168, tmdb_id=1668, overview="Six friends.", poster_path="/p.jpg"),
        enriched_at="2026-01-01T00:00:00+00:00",
    )
    # A second import knows only what the export knew.
    library.upsert_title(Title(name="Friends", kind=Kind.SHOW, tvdb_id=79168))
    row = library.conn.execute("SELECT overview, tmdb_id FROM titles WHERE id = ?", (title_id,)).fetchone()
    assert row["overview"] == "Six friends."
    assert row["tmdb_id"] == 1668


def test_recording_a_watch_creates_the_episode_it_names(library: Library) -> None:
    title_id = a_show(library)
    library.record_watch(title_id, Watch(watched_at="2018-05-12 01:10:14", episode=(1, 1)))
    assert [(e["season_number"], e["episode_number"]) for e in library.episodes(title_id)] == [(1, 1)]


def test_the_same_watch_imported_twice_is_stored_once(library: Library) -> None:
    title_id = a_show(library)
    watch = Watch(watched_at="2018-05-12 01:10:14", episode=(1, 1), source="tvtime")
    library.record_watch(title_id, watch)
    library.record_watch(title_id, watch)
    assert library.title(title_id).episodes_watched == 1
    assert library.stats()["watches"] == 1


def test_a_rewatch_is_a_second_row_not_a_duplicate(library: Library) -> None:
    title_id = a_show(library)
    library.record_watch(title_id, Watch(watched_at="2018-05-12 01:10:14", episode=(1, 1)))
    library.record_watch(title_id, Watch(watched_at="2021-04-23 00:23:28", episode=(1, 1), is_rewatch=True))
    assert library.stats()["watches"] == 2
    assert library.title(title_id).episodes_watched == 1


def test_a_film_watched_twice_on_the_same_day_is_stored_once(library: Library) -> None:
    title_id = library.upsert_title(Title(name="Arrival", kind=Kind.MOVIE, tmdb_id=329865))
    for _ in range(2):
        library.record_watch(title_id, Watch(watched_at="2026-01-01 20:00:00", source="tvtime"))
    assert library.stats()["watches"] == 1


def test_up_next_is_the_lowest_unwatched_episode_and_skips_specials(library: Library) -> None:
    title_id = a_show(library)
    library.set_state(title_id, TitleState(status=Status.WATCHING))
    for season, number in [(0, 1), (1, 1), (1, 2), (1, 3)]:
        library.upsert_episode(title_id, Episode(season_number=season, episode_number=number))
    # Watched out of order: 1 and 3, leaving a gap at 2.
    library.record_watch(title_id, Watch(watched_at="2020-01-01 00:00:00", episode=(1, 1)))
    library.record_watch(title_id, Watch(watched_at="2020-01-03 00:00:00", episode=(1, 3)))

    (row,) = library.up_next()
    assert (row["season_number"], row["episode_number"]) == (1, 2)


def test_up_next_ignores_titles_that_are_not_being_watched(library: Library) -> None:
    title_id = a_show(library)
    library.set_state(title_id, TitleState(status=Status.COMPLETED))
    library.upsert_episode(title_id, Episode(season_number=1, episode_number=1))
    assert library.up_next() == []


def test_titles_can_be_filtered_by_status_and_kind(library: Library) -> None:
    watching = a_show(library, "Friends", tvdb_id=1)
    completed = a_show(library, "Arrow", tvdb_id=2)
    film = library.upsert_title(Title(name="Arrival", kind=Kind.MOVIE, tmdb_id=329865))
    library.set_state(watching, TitleState(status=Status.WATCHING))
    library.set_state(completed, TitleState(status=Status.COMPLETED))
    library.set_state(film, TitleState(status=Status.COMPLETED))

    assert [t.name for t in library.titles(status=Status.WATCHING)] == ["Friends"]
    assert [t.name for t in library.titles(kind=Kind.MOVIE)] == ["Arrival"]
    assert len(library.titles()) == 3


def test_state_updates_keep_a_rating_the_new_state_does_not_carry(library: Library) -> None:
    title_id = a_show(library)
    library.set_state(title_id, TitleState(status=Status.WATCHING, rating=10))
    library.set_state(title_id, TitleState(status=Status.COMPLETED))
    row = library.title(title_id)
    assert (row.status, row.rating) == (Status.COMPLETED, 10)


def test_known_minutes_counts_episode_runtime_where_it_exists(library: Library) -> None:
    title_id = a_show(library)
    library.upsert_episode(title_id, Episode(season_number=1, episode_number=1, runtime=22))
    library.upsert_episode(title_id, Episode(season_number=1, episode_number=2))
    library.record_watch(title_id, Watch(watched_at="2020-01-01 00:00:00", episode=(1, 1)))
    library.record_watch(title_id, Watch(watched_at="2020-01-02 00:00:00", episode=(1, 2)))
    assert library.stats()["known_minutes"] == 22


def test_an_export_round_trips_into_the_library(library: Library, export_dir) -> None:
    count = library.ingest(read_export(export_dir))
    assert count == 5
    stats = library.stats()
    assert stats["watches"] == 4
    assert stats["by_status"] == {"watching": 1, "completed": 1, "stopped": 2, "watchlist": 1}
    assert library.ingest(read_export(export_dir)) == 5
    assert library.stats()["watches"] == 4


def test_only_unenriched_titles_are_listed_for_enrichment(library: Library) -> None:
    stale = a_show(library, "Friends", tvdb_id=1)
    done = a_show(library, "Arrow", tvdb_id=2)
    library.apply_enrichment(done, Title(name="Arrow", tvdb_id=2), enriched_at="2026-01-01T00:00:00+00:00")
    assert [t.id for t in library.needing_enrichment()] == [stale]


def test_a_bulk_marked_season_keeps_a_row_per_episode(library: Library) -> None:
    """TV Time stamps every episode of a bulk mark with the same timestamp."""
    title_id = a_show(library, "Beyblade", tvdb_id=70799)
    for source_id in ("4149573", "4149611", "4149650"):
        library.record_watch(
            library.title(title_id).id,
            Watch(watched_at="2019-01-01 00:00:00", source="tvtime", source_episode_id=source_id),
        )
    assert library.stats()["watches"] == 3
    # Re-importing the same export must not add a fourth.
    library.record_watch(
        title_id, Watch(watched_at="2019-01-01 00:00:00", source="tvtime", source_episode_id="4149573")
    )
    assert library.stats()["watches"] == 3


def test_unnumbered_watches_still_count_toward_the_title(library: Library) -> None:
    title_id = a_show(library, "Beyblade", tvdb_id=70799)
    library.record_watch(title_id, Watch(watched_at="2019-01-01 00:00:00", source="tvtime", source_episode_id="1"))
    row = library.title(title_id)
    # No episode to count, but the viewing is on record and dated.
    assert row.episodes_watched == 0
    assert row.last_watched_at == "2019-01-01 00:00:00"
