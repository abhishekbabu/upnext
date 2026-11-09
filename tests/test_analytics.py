from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo

from upnext.domain.analytics import BULK_RUN, TimedViewing, analyse, logged_in_bulk

UTC = ZoneInfo("UTC")
TODAY = date(2026, 6, 15)


def seen(watched_at: str, title_id: int = 1, name: str = "Friends", minutes: int | None = 22) -> TimedViewing:
    return TimedViewing(title_id=title_id, name=name, poster_path=None, watched_at=watched_at, minutes=minutes)


def test_a_season_ticked_off_at_once_is_logged_in_bulk_and_an_evening_is_not() -> None:
    catch_up = [seen(f"2017-03-07 05:27:{second:02d}") for second in range(BULK_RUN)]
    evening = [seen(f"2017-03-08 2{hour}:00:00") for hour in range(3)]
    noted_after = [seen(f"2017-03-09 23:00:{second:02d}") for second in range(BULK_RUN - 1)]

    bulk = logged_in_bulk(catch_up + evening + noted_after)

    assert bulk == set(range(BULK_RUN))


def test_a_bulk_run_is_followed_across_the_minute_it_spans() -> None:
    """A minute boundary is not a gap: the run is one catch-up wherever the clock ticks over."""
    run = [
        seen(f"2017-03-07 05:2{minute}:{second:02d}")
        for minute, second in [(7, 50), (7, 55), (8, 5), (8, 30), (8, 59), (9, 40)]
    ]
    assert logged_in_bulk(run) == set(range(6))


def test_bulk_viewings_count_toward_what_was_watched_but_not_when() -> None:
    catch_up = [seen(f"2017-03-07 05:27:{second:02d}", title_id=2, name="Arrow") for second in range(BULK_RUN)]
    watched = [seen("2018-05-12 21:00:00"), seen("2018-05-12 22:00:00")]

    activity = analyse(catch_up + watched, tz=UTC, today=TODAY)

    assert (activity.dated, activity.bulk) == (2, BULK_RUN)
    assert [t.name for t in activity.top_titles] == ["Arrow", "Friends"]
    assert [m.label for m in activity.months] == ["2018-05"]
    assert activity.busiest_day.date == "2018-05-12"


def test_hours_and_days_are_the_readers_own() -> None:
    """01:30 UTC on a Monday is 18:30 on Sunday in Los Angeles."""
    activity = analyse([seen("2026-06-15 01:30:00")], tz=ZoneInfo("America/Los_Angeles"), today=TODAY)

    sunday, monday = 6, 0
    assert activity.rhythm[sunday][18] == 1
    assert activity.rhythm[monday][1] == 0
    assert activity.months[0].label == "2026-06"
    assert activity.busiest_day.date == "2026-06-14"


def test_months_run_unbroken_from_first_to_last_so_a_gap_shows() -> None:
    activity = analyse([seen("2025-11-03 20:00:00"), seen("2026-02-01 20:00:00", minutes=None)], tz=UTC, today=TODAY)

    assert [(m.label, m.viewings, m.minutes) for m in activity.months] == [
        ("2025-11", 1, 22),
        ("2025-12", 0, 0),
        ("2026-01", 0, 0),
        ("2026-02", 1, 0),
    ]
    assert [(y.label, y.viewings, y.titles) for y in activity.years] == [("2025", 1, 1), ("2026", 1, 1)]


def test_the_longest_streak_and_one_still_running_through_yesterday() -> None:
    days = ["2026-01-01", "2026-01-02", "2026-01-03", "2026-06-13", "2026-06-14"]

    activity = analyse([seen(f"{day} 20:00:00") for day in days], tz=UTC, today=TODAY)

    longest = activity.longest_streak
    assert (longest.days, longest.start, longest.end) == (3, "2026-01-01", "2026-01-03")
    assert activity.current_streak == 2


def test_a_streak_that_missed_yesterday_is_over() -> None:
    activity = analyse([seen("2026-06-13 20:00:00")], tz=UTC, today=TODAY)
    assert activity.current_streak == 0


def test_the_biggest_binge_is_one_show_in_one_day() -> None:
    """Three shows in a day is a busy day, not a binge; two of one show is."""
    viewings = [
        seen("2026-01-01 18:00:00", title_id=1),
        seen("2026-01-01 19:00:00", title_id=2, name="Arrow"),
        seen("2026-01-01 20:00:00", title_id=3, name="Castle"),
        seen("2026-02-01 18:00:00", title_id=2, name="Arrow"),
        seen("2026-02-01 19:00:00", title_id=2, name="Arrow"),
    ]

    activity = analyse(viewings, tz=UTC, today=TODAY)

    assert (activity.busiest_day.date, activity.busiest_day.viewings) == ("2026-01-01", 3)
    binge = activity.biggest_binge
    assert (binge.name, binge.date, binge.viewings) == ("Arrow", "2026-02-01", 2)


def test_an_empty_library_has_nothing_to_report() -> None:
    activity = analyse([], tz=UTC, today=TODAY)

    assert (activity.months, activity.top_titles, activity.longest_streak, activity.busiest_day) == ([], [], None, None)
    assert activity.rhythm == [[0] * 24 for _ in range(7)]
