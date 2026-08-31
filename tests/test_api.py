from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

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
