from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from upnext.adapters.inbound.web import api as web_api
from upnext.adapters.inbound.web.api import app, get_settings
from upnext.adapters.outbound.store.db import connect
from upnext.adapters.outbound.store.library import Library
from upnext.config.settings import Settings
from upnext.domain.models import Episode, Status, Title, TitleState, Watch


@pytest.fixture
def api(tmp_path: Path) -> TestClient:
    db_path = tmp_path / "library.db"
    library = Library(connect(db_path))
    friends = library.upsert_title(Title(name="Friends", tvdb_id=79168, tmdb_id=1668, year=1994))
    library.set_state(friends, TitleState(status=Status.WATCHING, is_favorite=True, rating=10))
    for number in (1, 2, 3):
        library.upsert_episode(friends, Episode(season_number=1, episode_number=number, runtime=22))
    library.record_watch(friends, Watch(watched_at="2018-05-12 01:10:14", episode=(1, 1), source="tvtime"))

    arrow = library.upsert_title(Title(name="Arrow", tvdb_id=257655))
    library.set_state(arrow, TitleState(status=Status.COMPLETED))
    # What enrichment does after writing the episode list: a watch records what
    # the source called the episode, and is matched to a catalog one here.
    library.link_watches(friends)
    library.conn.commit()
    library.conn.close()

    app.dependency_overrides[get_settings] = lambda: Settings(db_path=db_path, tmdb_api_key="")
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health(api: TestClient) -> None:
    assert api.get("/api/health").json() == {"status": "ok"}


def test_titles_are_listed_with_their_progress(api: TestClient) -> None:
    body = api.get("/api/titles").json()
    friends = next(t for t in body if t["name"] == "Friends")
    assert friends["episodes_watched"] == 1
    assert friends["status"] == "watching"
    assert friends["is_favorite"] is True
    assert friends["rating"] == 10


def test_titles_can_be_filtered_by_status(api: TestClient) -> None:
    body = api.get("/api/titles", params={"status": "completed"}).json()
    assert [t["name"] for t in body] == ["Arrow"]


def test_an_unknown_status_is_rejected(api: TestClient) -> None:
    assert api.get("/api/titles", params={"status": "obsessed"}).status_code == 422


def test_a_title_comes_back_with_its_episodes(api: TestClient) -> None:
    title_id = api.get("/api/titles").json()[0]["id"]
    body = api.get(f"/api/titles/{title_id}").json()
    assert len(body["episodes"]) == 3
    assert body["episodes"][0]["watch_count"] == 1


def test_a_missing_title_is_a_404(api: TestClient) -> None:
    assert api.get("/api/titles/9999").status_code == 404


def test_up_next_is_the_next_unwatched_episode(api: TestClient) -> None:
    (row,) = api.get("/api/up-next").json()
    assert (row["name"], row["season_number"], row["episode_number"]) == ("Friends", 1, 2)


def test_the_up_next_limit_is_bounded(api: TestClient) -> None:
    assert api.get("/api/up-next", params={"limit": 0}).status_code == 422
    assert api.get("/api/up-next", params={"limit": 500}).status_code == 422


def test_stats_summarise_the_library(api: TestClient) -> None:
    body = api.get("/api/stats").json()
    assert body["episodes_watched"] == 1
    assert body["known_minutes"] == 22
    assert body["by_status"] == {"watching": 1, "completed": 1}


def test_config_hands_the_client_the_artwork_base(api: TestClient) -> None:
    """The client joins this to a poster_path with the size it wants."""
    assert api.get("/api/config").json() == {"image_base": "https://image.tmdb.org/t/p"}


def test_an_unknown_api_path_is_a_404_even_with_a_build_present(tmp_path: Path, monkeypatch) -> None:
    """Without this the SPA handler answers /api/typo with index.html and a 200.

    The failure then surfaces as JSON that will not parse, rather than as the
    missing route it is.
    """
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>upnext</title>", encoding="utf-8")

    app = FastAPI()
    monkeypatch.setattr(web_api, "app", app)
    monkeypatch.setattr(web_api, "DIST", dist)
    web_api.mount_web()

    with TestClient(app) as spa:
        assert spa.get("/api/nope").status_code == 404
        assert spa.get("/library").status_code == 200
        assert "upnext" in spa.get("/library").text


def test_without_a_build_the_api_still_serves(tmp_path: Path, monkeypatch) -> None:
    """A fresh clone has no web/dist, and `upnext serve` must still work."""
    app = FastAPI()
    monkeypatch.setattr(web_api, "app", app)
    monkeypatch.setattr(web_api, "DIST", tmp_path / "nothing-here")
    web_api.mount_web()

    with TestClient(app) as bare:
        assert bare.get("/").status_code == 404


def test_a_title_detail_carries_the_catalog_columns(tmp_path: Path) -> None:
    """The response model promises these; the read model has to actually hold them.

    `TitleRow` once stopped at what a shelf draws, so overview, artwork and the
    air dates were served as null however full the database was — a contract the
    API advertised and never met.
    """
    db_path = tmp_path / "library.db"
    library = Library(connect(db_path))
    title_id = library.upsert_title(Title(name="Avatar: The Last Airbender", tvdb_id=1))
    library.set_state(title_id, TitleState(status=Status.WATCHING))
    library.apply_enrichment(
        title_id,
        Title(
            name="Avatar: The Last Airbender",
            tmdb_id=82452,
            imdb_id="tt9018736",
            overview="A young boy known as the Avatar…",
            poster_path="/poster.jpg",
            backdrop_path="/backdrop.jpg",
            air_status="Returning Series",
            first_air_date="2024-02-22",
            last_air_date="2024-02-22",
            total_episodes=15,
            runtime=52,
        ),
        enriched_at="2026-01-01T00:00:00+00:00",
    )
    library.conn.commit()
    library.conn.close()

    app.dependency_overrides[get_settings] = lambda: Settings(db_path=db_path, tmdb_api_key="")
    try:
        body = TestClient(app).get(f"/api/titles/{title_id}").json()
    finally:
        app.dependency_overrides.clear()

    assert body["overview"] == "A young boy known as the Avatar…"
    assert body["backdrop_path"] == "/backdrop.jpg"
    assert body["first_air_date"] == "2024-02-22"
    assert body["last_air_date"] == "2024-02-22"
    assert body["imdb_id"] == "tt9018736"
    assert body["runtime"] == 52


def test_the_shelf_payload_stays_lean(api: TestClient) -> None:
    """A list of 160 titles does not carry 160 synopses.

    The read model holds every column; what crosses the wire is the response
    model's decision, and the shelf draws none of these.
    """
    first = api.get("/api/titles").json()[0]
    assert "overview" not in first
    assert "backdrop_path" not in first
