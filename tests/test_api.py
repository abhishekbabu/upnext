from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from upnext.adapters.inbound.web.api import app, get_library, get_settings, mount_web
from upnext.adapters.outbound.store.library import Library, open_library
from upnext.config.settings import PROJECT_ROOT, Settings
from upnext.domain.models import Episode, Status, Title, TitleState, Watch

type Serve = Callable[[Path], TestClient]


@pytest.fixture
def serve() -> Iterator[Serve]:
    """The app, reading the library at a given path."""

    def client(db_path: Path) -> TestClient:
        app.dependency_overrides[get_settings] = lambda: Settings(db_path=db_path, tmdb_api_key="")
        return TestClient(app)

    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def api(tmp_path: Path, serve: Serve) -> TestClient:
    db_path = tmp_path / "library.db"
    with open_library(db_path) as library:
        friends = library.upsert_title(Title(name="Friends", tvdb_id=79168, tmdb_id=1668, year=1994))
        library.set_state(friends, TitleState(status=Status.WATCHING, is_favorite=True, rating=10))
        for number in (1, 2, 3):
            library.upsert_episode(friends, Episode(season_number=1, episode_number=number, runtime=22))
        library.record_watch(friends, Watch(watched_at="2018-05-12 01:10:14", episode=(1, 1), source="tvtime"))
        library.link_watches(friends)

        arrow = library.upsert_title(Title(name="Arrow", tvdb_id=257655))
        library.set_state(arrow, TitleState(status=Status.COMPLETED))
    return serve(db_path)


def test_titles_are_listed_with_their_progress(api: TestClient) -> None:
    friends = next(t for t in api.get("/api/titles").json() if t["name"] == "Friends")
    assert (friends["episodes_watched"], friends["total_episodes"], friends["status"]) == (1, None, "watching")


def test_titles_can_be_filtered_by_status(api: TestClient) -> None:
    body = api.get("/api/titles", params={"status": "completed"}).json()
    assert [t["name"] for t in body] == ["Arrow"]


def test_an_unknown_status_is_rejected(api: TestClient) -> None:
    assert api.get("/api/titles", params={"status": "obsessed"}).status_code == 422


def test_a_title_comes_back_with_its_episodes(api: TestClient) -> None:
    title_id = api.get("/api/titles").json()[0]["id"]
    body = api.get(f"/api/titles/{title_id}").json()
    assert [e["watch_count"] for e in body["episodes"]] == [1, 0, 0]
    assert body["rating"] == 10


def test_a_missing_title_is_a_404(api: TestClient) -> None:
    assert api.get("/api/titles/9999").status_code == 404


def test_up_next_is_the_next_unwatched_episode(api: TestClient) -> None:
    (row,) = api.get("/api/up-next").json()
    assert (row["name"], row["season_number"], row["episode_number"]) == ("Friends", 1, 2)


def test_stats_summarise_the_library(api: TestClient) -> None:
    body = api.get("/api/stats").json()
    assert (body["distinct_episodes"], body["known_minutes"]) == (1, 22)
    assert body["by_status"] == {"watching": 1, "completed": 1}


def test_config_hands_the_client_the_artwork_base(api: TestClient) -> None:
    assert api.get("/api/config").json() == {"image_base": "https://image.tmdb.org/t/p"}


def test_a_title_detail_carries_what_enrichment_wrote(tmp_path: Path, serve: Serve) -> None:
    """The response model promises these; the read model has to actually hold them.

    `TitleRow` once stopped at what a shelf draws, so the overview was served
    as null however full the database was.
    """
    db_path = tmp_path / "library.db"
    with open_library(db_path) as library:
        title_id = library.upsert_title(Title(name="Avatar: The Last Airbender", tvdb_id=1))
        library.apply_enrichment(
            title_id,
            Title(name="Avatar: The Last Airbender", overview="A young boy…", air_status="Returning Series"),
            enriched_at="2026-01-01T00:00:00+00:00",
        )

    body = serve(db_path).get(f"/api/titles/{title_id}").json()
    assert (body["overview"], body["air_status"]) == ("A young boy…", "Returning Series")
    assert body["enriched_at"] == "2026-01-01T00:00:00+00:00"


def test_the_shelf_payload_stays_lean(api: TestClient) -> None:
    """A list of 160 titles does not carry 160 synopses."""
    assert "overview" not in api.get("/api/titles").json()[0]


@pytest.fixture
def timeline_api(tmp_path: Path, serve: Serve) -> TestClient:
    """One watched show with a past and a future episode, and one never watched.

    Its own fixture rather than the shared one because the calendar is the only
    thing it asserts, and adding a future episode to `Friends` would change what
    every other test there counts.
    """
    db_path = tmp_path / "timeline.db"
    recent = (datetime.now(UTC).date() - timedelta(days=5)).isoformat()
    with open_library(db_path) as library:
        lasso = library.upsert_title(Title(name="Ted Lasso", tmdb_id=97546))
        library.set_state(lasso, TitleState(status=Status.STOPPED))
        library.upsert_episode(lasso, Episode(season_number=1, episode_number=1, air_date="2000-01-01"))
        library.upsert_episode(lasso, Episode(season_number=4, episode_number=4, air_date=recent))
        library.upsert_episode(
            lasso, Episode(season_number=4, episode_number=5, name="Riches of Embarrassment", air_date="2099-01-01")
        )
        library.upsert_episode(lasso, Episode(season_number=4, episode_number=6, air_date="2099-01-08"))
        library.record_watch(lasso, Watch(watched_at="2023-01-01 00:00:00", episode=(1, 1), source="tvtime"))

        reacher = library.upsert_title(Title(name="Reacher", tmdb_id=108978))
        library.set_state(reacher, TitleState(status=Status.WATCHLIST))
        library.upsert_episode(reacher, Episode(season_number=4, episode_number=6, air_date="2099-01-02"))
    return serve(db_path)


def test_the_timeline_is_the_last_month_and_what_is_coming_of_watched_shows(timeline_api: TestClient) -> None:
    episodes = timeline_api.get("/api/timeline").json()["episodes"]
    assert [(e["name"], e["season_number"], e["episode_number"]) for e in episodes] == [
        ("Ted Lasso", 4, 4),
        ("Ted Lasso", 4, 5),
        ("Ted Lasso", 4, 6),
    ]
    assert (episodes[1]["air_date"], episodes[1]["episode_name"]) == ("2099-01-01", "Riches of Embarrassment")


def test_marking_an_episode_takes_it_off_the_timeline_and_unmarking_puts_it_back(timeline_api: TestClient) -> None:
    out_now = timeline_api.get("/api/timeline").json()["episodes"][0]["episode_id"]

    assert timeline_api.post(f"/api/episodes/{out_now}/watch").status_code == 204
    assert out_now not in [e["episode_id"] for e in timeline_api.get("/api/timeline").json()["episodes"]]

    assert timeline_api.delete(f"/api/episodes/{out_now}/watch").status_code == 204
    assert out_now in [e["episode_id"] for e in timeline_api.get("/api/timeline").json()["episodes"]]


def test_marking_or_unmarking_what_is_not_there_is_a_404(timeline_api: TestClient) -> None:
    assert timeline_api.post("/api/episodes/9999/watch").status_code == 404
    out_now = timeline_api.get("/api/timeline").json()["episodes"][0]["episode_id"]
    assert timeline_api.delete(f"/api/episodes/{out_now}/watch").status_code == 404


def test_the_timeline_says_which_day_it_is(timeline_api: TestClient) -> None:
    """The client labels "Today" and "Tomorrow" against this, not its own clock."""
    assert timeline_api.get("/api/timeline").json()["today"] == datetime.now(UTC).date().isoformat()


@pytest.fixture
def built(tmp_path: Path) -> Iterator[TestClient]:
    """An app serving a front end build, with one hashed asset."""
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>upnext</title>", encoding="utf-8")
    (dist / "assets" / "index-abc123.js").write_text("console.log(1)", encoding="utf-8")
    spa = FastAPI()
    mount_web(spa, dist)
    with TestClient(spa) as client:
        yield client


def test_an_unknown_api_path_is_a_404_even_with_a_build_present(built: TestClient) -> None:
    """Without this the SPA handler answers /api/typo with index.html and a 200,
    and the failure surfaces as JSON that will not parse."""
    assert built.get("/api/nope").status_code == 404
    assert "upnext" in built.get("/library").text


def test_a_path_cannot_climb_out_of_the_build(built: TestClient, tmp_path: Path) -> None:
    """The page handler joins the request path to dist/; `..` must not leave it."""
    (tmp_path / "secret.txt").write_text("not for the browser", encoding="utf-8")
    assert "not for the browser" not in built.get("/..%2Fsecret.txt").text


def test_the_page_revalidates_and_its_hashed_assets_do_not(built: TestClient) -> None:
    """A rebuilt front end has to reach a browser that has been here before.

    index.html keeps its name and names this build's bundle, so a browser left
    to its own heuristics serves yesterday's app. Everything under assets/ has
    a content hash in its filename, so the old one can be kept for good.
    """
    assert built.get("/").headers["cache-control"] == "no-cache"
    assert built.get("/library").headers["cache-control"] == "no-cache"
    assert "immutable" in built.get("/assets/index-abc123.js").headers["cache-control"]


def test_without_a_build_the_api_still_serves(tmp_path: Path) -> None:
    """A fresh clone has no web/dist, and `upnext serve` must still work."""
    bare = FastAPI()
    mount_web(bare, tmp_path / "nothing-here")
    with TestClient(bare) as client:
        assert client.get("/").status_code == 404


def test_the_web_layer_opens_connections_it_can_use_off_thread() -> None:
    """The API's connections must outlive the thread that opened them.

    FastAPI hands the dependency, the endpoint it feeds and the teardown three
    separately borrowed threadpool threads. Asserted on `get_library` rather
    than through `TestClient`, which drives the app from a single thread and
    never reproduces it.
    """
    # The generator is held, not just advanced: dropping it closes the
    # connection, and the failure becomes a closed database instead of the
    # cross-thread one under test.
    connections = get_library(Settings(db_path=":memory:", tmdb_api_key=""))
    library: Library = next(connections)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(lambda: library.stats().watches).result() == 0
    finally:
        connections.close()


def test_the_client_schema_matches_the_api() -> None:
    """`web/openapi.json` is what the client's types are generated from.

    A wire model changed without regenerating it would leave the client
    typechecking against yesterday's API. Run `just api-types` to fix.
    """
    committed = json.loads((PROJECT_ROOT / "web" / "openapi.json").read_text(encoding="utf-8"))
    assert committed == json.loads(json.dumps(app.openapi()))


def test_a_title_id_sqlite_cannot_hold_is_a_422_not_a_500(api: TestClient) -> None:
    assert api.get(f"/api/titles/{2**64}").status_code == 422
