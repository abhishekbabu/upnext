"""When and what the library was watched: the figures behind the stats page.

Pure: the store loads every viewing once and this turns them into figures, so
each rule below can be tested without a database.

A viewing's timestamp is when it was *logged*, which is usually when it was
watched — but not when a season, or a whole back-catalogue, was ticked off at
once. TV Time stamps those with the moment of the tick: 207 episodes at one
second, 625 on one day. Read as viewing times they would put the busiest day
and the favourite hour wherever someone caught their history up. So a run of
`BULK_RUN` or more viewings logged under `BULK_GAP` apart is set aside as
logged in bulk. It still counts toward what was watched — the totals and the
top titles — but not toward anything about *when*.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

BULK_GAP = timedelta(seconds=60)
"""Nobody watches an episode in a minute. Viewings closer than this were logged together."""

BULK_RUN = 6
"""How many viewings logged together make a catch-up rather than a binge noted
afterwards. Five episodes ticked off after an evening's viewing are still
roughly when they were watched; a season of them is not."""

TOP_TITLES = 10


@dataclass(slots=True, frozen=True)
class TimedViewing:
    """One viewing, as the analysis needs it."""

    title_id: int
    name: str
    poster_path: str | None
    watched_at: str
    """ISO 8601; read as UTC when it carries no offset, as every source and upnext itself write it."""
    minutes: int | None
    """The episode's runtime, or the show's typical one; None before enrichment."""


@dataclass(slots=True)
class Period:
    label: str
    """`YYYY-MM` for a month, `YYYY` for a year."""
    viewings: int = 0
    minutes: int = 0
    titles: int = 0


@dataclass(slots=True)
class TitleTotal:
    title_id: int
    name: str
    poster_path: str | None
    viewings: int = 0
    minutes: int = 0


@dataclass(slots=True)
class Streak:
    days: int
    start: str
    end: str


@dataclass(slots=True)
class Day:
    date: str
    viewings: int


@dataclass(slots=True)
class Binge:
    title_id: int
    name: str
    date: str
    viewings: int


@dataclass(slots=True)
class Activity:
    timezone: str
    dated: int = 0
    """Viewings whose timestamp says when they were watched."""
    bulk: int = 0
    """Viewings logged in bulk, left out of everything about when."""

    months: list[Period] = field(default_factory=list)
    """Every month from the first dated viewing to the last, empty ones included,
    so a gap in the chart is a gap in the watching."""
    years: list[Period] = field(default_factory=list)
    rhythm: list[list[int]] = field(default_factory=list)
    """Viewings by weekday (Monday first) and hour, in the reader's timezone."""
    top_titles: list[TitleTotal] = field(default_factory=list)
    longest_streak: Streak | None = None
    current_streak: int = 0
    """Consecutive days with a viewing, ending today or yesterday — a streak
    is not broken by a day that has not finished."""
    busiest_day: Day | None = None
    biggest_binge: Binge | None = None


def analyse(viewings: list[TimedViewing], *, tz: ZoneInfo, today: date) -> Activity:
    """Everything the stats page draws, in `tz`, with `today` as the day in `tz`."""
    activity = Activity(timezone=str(tz))
    activity.top_titles = _top_titles(viewings)

    bulk = logged_in_bulk(viewings)
    dated = [(v, _local(v.watched_at, tz)) for i, v in enumerate(viewings) if i not in bulk]
    activity.dated, activity.bulk = len(dated), len(bulk)

    activity.months = _periods(dated, key=lambda at: at.strftime("%Y-%m"), fill=_months_between)
    activity.years = _periods(dated, key=lambda at: at.strftime("%Y"), fill=_years_between)

    rhythm = [[0] * 24 for _ in range(7)]
    for _, at in dated:
        rhythm[at.weekday()][at.hour] += 1
    activity.rhythm = rhythm

    days = Counter(at.date() for _, at in dated)
    activity.longest_streak, activity.current_streak = _streaks(set(days), today)
    if days:
        # Ties go to the earliest, so the answer does not move between runs.
        day, count = min(days.items(), key=lambda item: (-item[1], item[0]))
        activity.busiest_day = Day(date=day.isoformat(), viewings=count)

    binges = Counter((v.title_id, at.date()) for v, at in dated)
    if binges:
        (title_id, day), count = min(binges.items(), key=lambda item: (-item[1], item[0][1], item[0][0]))
        name = next(v.name for v, _ in dated if v.title_id == title_id)
        activity.biggest_binge = Binge(title_id=title_id, name=name, date=day.isoformat(), viewings=count)
    return activity


def logged_in_bulk(viewings: list[TimedViewing]) -> set[int]:
    """Indexes of the viewings logged in a run of `BULK_RUN` or more, each under `BULK_GAP` from the last."""
    order = sorted(range(len(viewings)), key=lambda i: viewings[i].watched_at)
    bulk: set[int] = set()
    run: list[int] = []
    previous: datetime | None = None
    for i in order:
        at = _utc(viewings[i].watched_at)
        if previous is not None and at - previous >= BULK_GAP:
            if len(run) >= BULK_RUN:
                bulk.update(run)
            run = []
        run.append(i)
        previous = at
    if len(run) >= BULK_RUN:
        bulk.update(run)
    return bulk


def _top_titles(viewings: list[TimedViewing]) -> list[TitleTotal]:
    totals: dict[int, TitleTotal] = {}
    for v in viewings:
        total = totals.setdefault(v.title_id, TitleTotal(v.title_id, v.name, v.poster_path))
        total.viewings += 1
        total.minutes += v.minutes or 0
    ranked = sorted(totals.values(), key=lambda t: (-t.viewings, -t.minutes, t.name))
    return ranked[:TOP_TITLES]


def _periods(
    dated: list[tuple[TimedViewing, datetime]],
    *,
    key: Callable[[datetime], str],
    fill: Callable[[str, str], list[str]],
) -> list[Period]:
    if not dated:
        return []
    periods: dict[str, Period] = {}
    titles: dict[str, set[int]] = defaultdict(set)
    for v, at in dated:
        label = key(at)
        period = periods.setdefault(label, Period(label))
        period.viewings += 1
        period.minutes += v.minutes or 0
        titles[label].add(v.title_id)
    for label, ids in titles.items():
        periods[label].titles = len(ids)
    return [periods.get(label) or Period(label) for label in fill(min(periods), max(periods))]


def _months_between(first: str, last: str) -> list[str]:
    year, month = int(first[:4]), int(first[5:])
    labels = []
    while (label := f"{year:04d}-{month:02d}") <= last:
        labels.append(label)
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return labels


def _years_between(first: str, last: str) -> list[str]:
    return [str(year) for year in range(int(first), int(last) + 1)]


def _streaks(days: set[date], today: date) -> tuple[Streak | None, int]:
    longest: Streak | None = None
    for day in sorted(days):
        if day - timedelta(days=1) in days:
            continue  # Not the start of a run.
        end = day
        while end + timedelta(days=1) in days:
            end += timedelta(days=1)
        length = (end - day).days + 1
        if longest is None or length > longest.days:
            longest = Streak(days=length, start=day.isoformat(), end=end.isoformat())

    current = 0
    cursor = today if today in days else today - timedelta(days=1)
    while cursor in days:
        current += 1
        cursor -= timedelta(days=1)
    return longest, current


def _utc(stamp: str) -> datetime:
    at = datetime.fromisoformat(stamp)
    return at.replace(tzinfo=UTC) if at.tzinfo is None else at.astimezone(UTC)


def _local(stamp: str, tz: ZoneInfo) -> datetime:
    return _utc(stamp).astimezone(tz)
