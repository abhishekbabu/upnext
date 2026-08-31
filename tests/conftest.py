from __future__ import annotations

import csv
from pathlib import Path

import pytest

from upnext.adapters.outbound.store.db import connect
from upnext.adapters.outbound.store.library import Library
from upnext.domain.models import Episode, Kind, Title
from upnext.domain.ports import CatalogMatch, CatalogShow


@pytest.fixture(autouse=True)
def _isolate_from_local_env(request, monkeypatch, tmp_path_factory):
    """Keep the suite off this machine's key and library.

    `settings.py` finds `.env` by absolute path on purpose, so that `upnext`
    works from any directory — which also means a test calling `load_settings()`
    would read the real key off a developer's disk and nothing off CI's. The
    same test would then pass here and fail there, or worse, quietly reach TMDB.

    Environment variables win over the dotenv file in pydantic-settings, so
    setting them empty is enough. Integration tests are exempt: reaching TMDB is
    the whole of their job, and they skip themselves when there is no key.
    """
    if request.node.get_closest_marker("integration"):
        return
    monkeypatch.setenv("UPNEXT_TMDB_API_KEY", "")
    monkeypatch.setenv("UPNEXT_DB_PATH", str(tmp_path_factory.mktemp("library") / "library.db"))


@pytest.fixture
def library():
    conn = connect(":memory:")
    try:
        yield Library(conn)
    finally:
        conn.close()


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture(name="write_csv")
def write_csv_fixture():
    """The CSV writer as a fixture, so tests can amend an export in place."""
    return write_csv


@pytest.fixture(name="watch_row")
def watch_row_fixture():
    """The tracking-record builder, for tests that write their own history."""
    return row


@pytest.fixture
def export_dir(tmp_path: Path) -> Path:
    """A miniature TV Time export with one show of each status.

    The column sets match a real export exactly, including the columns upnext
    ignores, so a change that starts reading one of them is exercised here.
    """
    write_csv(
        tmp_path / "tracking-prod-records-v2.csv",
        ["user_id", "created_at", "s_id", "ep_id", "gsi", "key", "series_name", "season_number", "episode_number"],
        [
            # Friends: two episodes watched, one of them twice.
            row("2018-05-12 01:10:14", "79168", "303821", "watch-episode-1", "Friends", 1, 1),
            row("2018-05-12 01:30:03", "79168", "303822", "watch-episode-2", "Friends", 1, 2),
            row("2021-04-23 00:23:28", "79168", "303821", "rewatch-episode-3", "Friends", 1, 1),
            # Arrow: watched, then archived.
            row("2020-01-02 03:04:05", "257655", "5054712", "watch-episode-4", "Arrow", 3, 13),
            # A row upnext must ignore: not an episode watch.
            row("2020-01-02 03:04:05", "257655", "", "user-series-5", "Arrow", None, None),
        ],
    )
    write_csv(
        tmp_path / "followed_tv_show.csv",
        ["updated_at", "tv_show_name", "user_id", "tv_show_id", "archived", "created_at", "active"],
        [
            {
                "updated_at": "2024-01-01 00:00:00",
                "tv_show_name": "Friends",
                "user_id": "1",
                "tv_show_id": "79168",
                "archived": "0",
                "created_at": "2017-03-07 05:25:05",
                "active": "1",
            },
            {
                "updated_at": "2024-01-01 00:00:00",
                "tv_show_name": "Arrow",
                "user_id": "1",
                "tv_show_id": "257655",
                "archived": "1",
                "created_at": "2018-01-01 00:00:00",
                "active": "1",
            },
            {
                "updated_at": "2024-01-01 00:00:00",
                "tv_show_name": "Beyblade",
                "user_id": "1",
                "tv_show_id": "70799",
                "archived": "0",
                "created_at": "2017-03-07 05:27:58",
                "active": "0",
            },
        ],
    )
    write_csv(
        tmp_path / "user_tv_show_data.csv",
        ["nb_episodes_seen", "tv_show_name", "user_id", "tv_show_id", "is_followed", "is_favorited"],
        [
            {
                "nb_episodes_seen": "236",
                "tv_show_name": "Friends",
                "user_id": "1",
                "tv_show_id": "79168",
                "is_followed": "1",
                "is_favorited": "1",
            },
            {
                "nb_episodes_seen": "239",
                "tv_show_name": "Arrow",
                "user_id": "1",
                "tv_show_id": "257655",
                "is_followed": "1",
                "is_favorited": "0",
            },
            {
                "nb_episodes_seen": "154",
                "tv_show_name": "Beyblade",
                "user_id": "1",
                "tv_show_id": "70799",
                "is_followed": "0",
                "is_favorited": "0",
            },
            # Known only here — the export has no per-episode rows for it.
            {
                "nb_episodes_seen": "5",
                "tv_show_name": "The Flash (2014)",
                "user_id": "1",
                "tv_show_id": "279121",
                "is_followed": "0",
                "is_favorited": "0",
            },
        ],
    )
    write_csv(
        tmp_path / "user_show_special_status.csv",
        ["user_id", "tv_show_id", "status", "created_at", "updated_at", "tv_show_name"],
        [
            {
                "user_id": "1",
                "tv_show_id": "79168",
                "status": "favorite",
                "created_at": "2018-10-12 06:05:21",
                "updated_at": "2018-10-12 06:05:21",
                "tv_show_name": "Friends",
            },
            {
                "user_id": "1",
                "tv_show_id": "75382",
                "status": "for_later",
                "created_at": "2022-06-01 07:00:03",
                "updated_at": "2022-06-01 07:00:03",
                "tv_show_name": "The Ultimate Fighter",
            },
        ],
    )
    write_csv(
        tmp_path / "tv_show_rate.csv",
        ["tv_show_id", "rating", "created_at", "updated_at", "tv_show_name", "user_id"],
        [
            {
                "tv_show_id": "79168",
                "rating": "5",
                "created_at": "2017-11-03 05:48:02",
                "updated_at": "2017-11-03 05:48:02",
                "tv_show_name": "Friends",
                "user_id": "1",
            }
        ],
    )
    return tmp_path


def row(created_at, s_id, ep_id, key, series, season, episode) -> dict:
    return {
        "user_id": "1",
        "created_at": created_at,
        "s_id": s_id,
        "ep_id": ep_id,
        "gsi": "watch-episode-1619137408",
        "key": key,
        "series_name": series,
        "season_number": "" if season is None else str(season),
        "episode_number": "" if episode is None else str(episode),
    }


# ── the catalog, without TMDB ───────────────────────────────────────────

FRIENDS = Title(
    name="Friends",
    kind=Kind.SHOW,
    year=1994,
    tmdb_id=1668,
    tvdb_id=79168,
    imdb_id="tt0108778",
    air_status="Ended",
    first_air_date="1994-09-22",
    total_episodes=236,
    runtime=22,
)

FRIENDS_EPISODES = [
    Episode(season_number=0, episode_number=1, name="Special", tmdb_id=90),
    Episode(season_number=1, episode_number=1, name="The One Where It Begins", runtime=22, tmdb_id=1),
    Episode(season_number=1, episode_number=2, name="The One With the Sonogram", runtime=22, tmdb_id=2),
]


class FakeCatalog:
    """The `Catalog` port, without TMDB.

    One fake for one port, here rather than in each module that needs it — a
    second fake for the same port is how two tests come to disagree about what
    the real thing does.

    Speaks domain types because the port does. A fake that had to build TMDB's
    JSON would be testing the adapter's translation a second time, in the wrong
    place, and would go stale the day a second catalog appeared.
    """

    def __init__(
        self,
        *,
        found: CatalogMatch | None = None,
        search_results: list[CatalogMatch] | None = None,
        title: Title | None = None,
        episodes: list[Episode] | None = None,
    ) -> None:
        self.found = found
        self.search_results = search_results or []
        self.title = title or FRIENDS
        self.episodes = FRIENDS_EPISODES if episodes is None else episodes
        self.searched: list[str] = []

    def find_by_tvdb(self, tvdb_id: int) -> CatalogMatch | None:
        return self.found

    def search_shows(self, name: str, *, year: int | None = None) -> list[CatalogMatch]:
        self.searched.append(name)
        return self.search_results

    def fetch_show(self, catalog_id: int) -> CatalogShow:
        return CatalogShow(title=self.title, episodes=self.episodes)


def one_show(name: str, tmdb_id: int, episodes: list[tuple[int, int]]) -> FakeCatalog:
    """A catalog holding a single show, for the cases that only need a target."""
    return FakeCatalog(
        title=Title(name=name, tmdb_id=tmdb_id, total_episodes=len(episodes)),
        episodes=[Episode(season_number=s, episode_number=n) for s, n in episodes],
    )
