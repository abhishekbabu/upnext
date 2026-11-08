from __future__ import annotations

from pathlib import Path

import pytest

from upnext.adapters.outbound.store.library import Library, open_library
from upnext.domain.errors import NotFoundError
from upnext.domain.models import Episode, Kind, Status, Title, TitleState, Watch


def a_show(library: Library, name: str = "Friends", **kwargs) -> int:
    return library.upsert_title(Title(name=name, kind=Kind.SHOW, **kwargs))


def a_followed_show(library: Library, name: str = "Friends") -> int:
    title_id = a_show(library, name=name)
    library.set_state(title_id, TitleState(status=Status.WATCHING))
    return title_id


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


def test_a_film_watched_twice_on_the_same_day_is_stored_once(library: Library) -> None:
    title_id = library.upsert_title(Title(name="Arrival", kind=Kind.MOVIE, tmdb_id=329865))
    for _ in range(2):
        library.record_watch(title_id, Watch(watched_at="2026-01-01 20:00:00", source="tvtime"))
    assert library.stats().watches == 1


def test_up_next_is_the_lowest_unwatched_episode_and_skips_specials(library: Library) -> None:
    title_id = a_show(library)
    library.set_state(title_id, TitleState(status=Status.WATCHING))
    for season, number in [(0, 1), (1, 1), (1, 2), (1, 3)]:
        library.upsert_episode(title_id, Episode(season_number=season, episode_number=number))
    # Watched out of order: 1 and 3, leaving a gap at 2.
    library.record_watch(title_id, Watch(watched_at="2020-01-01 00:00:00", episode=(1, 1)))
    library.record_watch(title_id, Watch(watched_at="2020-01-03 00:00:00", episode=(1, 3)))
    library.link_watches(title_id)

    (row,) = library.up_next()
    assert (row.season_number, row.episode_number) == (1, 2)


def test_up_next_ignores_titles_that_are_not_being_watched(library: Library) -> None:
    title_id = a_show(library)
    library.set_state(title_id, TitleState(status=Status.COMPLETED))
    library.upsert_episode(title_id, Episode(season_number=1, episode_number=1))
    assert library.up_next() == []


def test_titles_can_be_filtered_by_status(library: Library) -> None:
    watching = a_show(library, "Friends", tvdb_id=1)
    completed = a_show(library, "Arrow", tvdb_id=2)
    library.set_state(watching, TitleState(status=Status.WATCHING))
    library.set_state(completed, TitleState(status=Status.COMPLETED))

    assert [t.name for t in library.titles(status=Status.WATCHING)] == ["Friends"]
    assert len(library.titles()) == 2


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
    library.link_watches(title_id)
    assert library.stats().known_minutes == 22


def test_count_titles_counts_everything_stored(library: Library) -> None:
    assert library.count_titles() == 0
    a_show(library, "Friends", tvdb_id=1)
    assert library.count_titles() == 1


def test_only_unenriched_titles_are_listed_for_enrichment(library: Library) -> None:
    stale = a_show(library, "Friends", tvdb_id=1)
    done = a_show(library, "Arrow", tvdb_id=2)
    library.apply_enrichment(done, Title(name="Arrow", tvdb_id=2), enriched_at="2026-01-01T00:00:00+00:00")
    assert [t.id for t in library.needing_enrichment()] == [stale]


def test_a_limit_takes_the_first_titles_by_name_and_none_takes_all(library: Library) -> None:
    for tvdb_id, name in enumerate(["Lost", "Arrow", "Friends"], start=1):
        a_show(library, name, tvdb_id=tvdb_id)
    assert [t.name for t in library.needing_enrichment(limit=2)] == ["Arrow", "Friends"]
    assert [t.name for t in library.needing_enrichment()] == ["Arrow", "Friends", "Lost"]


def test_a_bulk_marked_season_keeps_a_row_per_episode(library: Library) -> None:
    """TV Time stamps every episode of a bulk mark with the same timestamp."""
    title_id = a_show(library, "Beyblade", tvdb_id=70799)
    for source_id in ("4149573", "4149611", "4149650"):
        library.record_watch(
            library.title(title_id).id,
            Watch(watched_at="2019-01-01 00:00:00", source="tvtime", source_episode_id=source_id),
        )
    assert library.stats().watches == 3
    # Re-importing the same export must not add a fourth.
    library.record_watch(
        title_id, Watch(watched_at="2019-01-01 00:00:00", source="tvtime", source_episode_id="4149573")
    )
    assert library.stats().watches == 3


def test_unnumbered_watches_still_count_toward_the_title(library: Library) -> None:
    title_id = a_show(library, "Beyblade", tvdb_id=70799)
    library.record_watch(title_id, Watch(watched_at="2019-01-01 00:00:00", source="tvtime", source_episode_id="1"))
    row = library.title(title_id)
    # No episode to count, but the viewing is on record and dated.
    assert row.episodes_watched == 0
    assert row.last_watched_at == "2019-01-01 00:00:00"


TODAY = "2026-06-15"


def test_the_timeline_starts_where_it_is_told(library: Library) -> None:
    """The day given is in; the day before it is the backlog's."""
    title_id = a_followed_show(library)
    library.upsert_episode(title_id, Episode(season_number=1, episode_number=1, air_date="2026-06-14"))
    library.upsert_episode(title_id, Episode(season_number=1, episode_number=2, air_date=TODAY))
    library.record_watch(title_id, Watch(watched_at="2020-01-01 00:00:00", episode=(1, 1)))

    timeline = library.timeline(since=TODAY)
    assert [row.air_date for row in timeline] == [TODAY]


def test_the_timeline_is_for_shows_still_followed(library: Library) -> None:
    """Stopped and archived shows stay off it; a watchlisted one already started is on it."""
    for name, status in [
        ("Stick", Status.WATCHING),
        ("Percy Jackson", Status.WATCHLIST),
        ("Last Week Tonight", Status.COMPLETED),
        ("Ted Lasso", Status.STOPPED),
    ]:
        title_id = a_show(library, name=name)
        library.set_state(title_id, TitleState(status=status))
        library.upsert_episode(title_id, Episode(season_number=2, episode_number=1, air_date="2026-07-01"))
        library.record_watch(title_id, Watch(watched_at="2023-01-01 00:00:00", episode=(1, 1)))

    assert [row.name for row in library.timeline(since=TODAY)] == ["Percy Jackson", "Stick"]


def test_the_timeline_ignores_a_show_never_watched(library: Library) -> None:
    """A scheduled episode of something never seen is not "up next" for anyone.

    An enriched library is full of these: anything on the watchlist, and every
    show followed and then abandoned before an episode was logged.
    """
    unwatched = a_show(library, name="Reacher")
    library.set_state(unwatched, TitleState(status=Status.WATCHLIST))
    library.upsert_episode(unwatched, Episode(season_number=4, episode_number=6, air_date="2026-07-01"))

    assert library.timeline(since=TODAY) == []


def test_the_timeline_skips_specials_and_episodes_with_no_date(library: Library) -> None:
    """Season 0 is never the next thing to watch, and an undated episode is unscheduled."""
    title_id = a_followed_show(library)
    library.upsert_episode(title_id, Episode(season_number=0, episode_number=1, air_date="2026-07-01"))
    library.upsert_episode(title_id, Episode(season_number=2, episode_number=1, air_date=None))
    library.upsert_episode(title_id, Episode(season_number=2, episode_number=2, air_date="2026-07-02"))
    library.record_watch(title_id, Watch(watched_at="2020-01-01 00:00:00", episode=(2, 1)))

    timeline = library.timeline(since=TODAY)
    assert [(row.season_number, row.episode_number) for row in timeline] == [(2, 2)]


def test_the_timeline_is_ordered_by_the_calendar_across_shows(library: Library) -> None:
    """The soonest episode leads, whichever show it belongs to."""
    for name, air_date in [("Stick", "2026-11-03"), ("Chad Powers", "2026-09-03"), ("Shark Tank", "2026-09-30")]:
        title_id = a_followed_show(library, name=name)
        library.upsert_episode(title_id, Episode(season_number=2, episode_number=1, air_date=air_date))
        library.record_watch(title_id, Watch(watched_at="2020-01-01 00:00:00", episode=(1, 1)))

    timeline = library.timeline(since=TODAY)
    assert [row.name for row in timeline] == ["Chad Powers", "Shark Tank", "Stick"]


def test_reopening_a_library_leaves_it_as_it_was(tmp_path: Path) -> None:
    """The schema is applied on every connect, so applying it has to be a no-op
    on a library that already has it."""
    db_path = tmp_path / "library.db"
    with open_library(db_path) as library:
        title_id = library.upsert_title(Title(name="Friends", tvdb_id=79168))
        library.set_state(title_id, TitleState(status=Status.WATCHING))
        library.upsert_episode(title_id, Episode(season_number=1, episode_number=1))
        library.record_watch(title_id, Watch(watched_at="2018-05-12 01:10:14", episode=(1, 1)))
        library.link_watches(title_id)

    with open_library(db_path) as library:
        row = library.title(title_id)
    assert row is not None
    assert (row.status, row.episodes_watched) == (Status.WATCHING, 1)


def test_the_schema_accepts_every_status_the_domain_has(library: Library) -> None:
    """`title_state.status` has a CHECK that spells the enum out again."""
    for status in Status:
        library.set_state(library.upsert_title(Title(name=status)), TitleState(status=status))
    assert set(library.stats().by_status) == set(Status)


def test_an_episode_leaves_the_timeline_once_watched(library: Library) -> None:
    title_id = a_followed_show(library)
    library.upsert_episode(title_id, Episode(season_number=2, episode_number=1, air_date=TODAY))
    library.record_watch(title_id, Watch(watched_at="2020-01-01 00:00:00", episode=(1, 1)))
    (episode,) = library.timeline(since=TODAY)

    library.mark_watched(episode.episode_id, watched_at="2026-06-15 21:00:00")

    assert library.timeline(since=TODAY) == []


def test_marking_records_a_linked_viewing_and_refiles_the_show_as_watching(library: Library) -> None:
    """A new season of a show filed `stopped` is being watched again."""
    title_id = a_show(library)
    library.set_state(title_id, TitleState(status=Status.STOPPED, rating=8))
    library.upsert_episode(title_id, Episode(season_number=2, episode_number=1))
    (episode,) = library.episodes(title_id)

    library.mark_watched(episode.id, watched_at="2026-06-15 21:00:00")
    library.mark_watched(episode.id, watched_at="2026-06-16 21:00:00")

    (episode,) = library.episodes(title_id)
    assert (episode.watch_count, episode.marked_here) == (2, True)
    row = library.title(title_id)
    assert (row.status, row.rating, row.episodes_watched) == (Status.WATCHING, 8, 1)
    # A relink leaves it where it is: it was recorded in the catalog's numbering.
    library.link_watches(title_id)
    assert library.title(title_id).episodes_watched == 1


def test_unmarking_takes_back_only_what_upnext_marked(library: Library) -> None:
    title_id = a_show(library)
    library.upsert_episode(title_id, Episode(season_number=1, episode_number=1))
    library.record_watch(title_id, Watch(watched_at="2018-05-12 01:10:14", episode=(1, 1), source="tvtime"))
    library.link_watches(title_id)
    (episode,) = library.episodes(title_id)
    assert not episode.marked_here
    with pytest.raises(NotFoundError):
        library.unmark_watched(episode.id)

    library.mark_watched(episode.id, watched_at="2026-06-15 21:00:00")
    library.unmark_watched(episode.id)

    (episode,) = library.episodes(title_id)
    assert (episode.watch_count, episode.marked_here) == (1, False)


def test_marking_an_episode_that_does_not_exist_says_so(library: Library) -> None:
    with pytest.raises(NotFoundError):
        library.mark_watched(999, watched_at="2026-06-15 21:00:00")
