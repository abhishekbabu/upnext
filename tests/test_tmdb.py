from __future__ import annotations

import pytest
import requests

from upnext.catalog.tmdb import (
    RetryableTMDBError,
    TMDBClient,
    TMDBError,
    episodes_from_season,
    title_from_movie,
    title_from_show,
)
from upnext.models import Kind


class FakeResponse:
    def __init__(self, status_code: int = 200, payload: dict | None = None, headers: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}
        self.text = str(self._payload)

    @property
    def ok(self) -> bool:
        return self.status_code < 400

    def json(self) -> dict:
        return self._payload


class FakeSession:
    """Records every call and replays a queued list of responses."""

    def __init__(self, *responses) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, dict]] = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params or {}))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def client(session: FakeSession) -> TMDBClient:
    return TMDBClient("key", min_interval_seconds=0, session=session)


@pytest.fixture(autouse=True)
def no_backoff_sleep(monkeypatch) -> None:
    """Keep tenacity's exponential wait from putting seconds into the suite."""
    monkeypatch.setattr(TMDBClient.get.retry, "sleep", lambda _: None)


def test_a_missing_key_fails_before_any_request() -> None:
    with pytest.raises(TMDBError, match="No TMDB API key"):
        TMDBClient("")


def test_the_key_and_language_are_sent_on_every_request() -> None:
    session = FakeSession(FakeResponse(payload={"id": 1668}))
    client(session).show(1668)
    _, params = session.calls[0]
    assert params["api_key"] == "key"
    assert params["language"] == "en-US"


def test_a_timeout_is_retried_and_then_succeeds() -> None:
    session = FakeSession(requests.Timeout("slow"), FakeResponse(payload={"id": 1668}))
    assert client(session).show(1668) == {"id": 1668}
    assert len(session.calls) == 2


def test_a_rate_limit_is_retried(monkeypatch) -> None:
    monkeypatch.setattr("upnext.catalog.tmdb.time.sleep", lambda _: None)
    session = FakeSession(FakeResponse(429, headers={"Retry-After": "0"}), FakeResponse(payload={"id": 1}))
    assert client(session).show(1) == {"id": 1}


def test_retries_give_up_and_surface_the_failure() -> None:
    session = FakeSession(*[FakeResponse(503) for _ in range(4)])
    with pytest.raises(RetryableTMDBError):
        client(session).show(1)
    assert len(session.calls) == 4


def test_a_404_is_not_retried() -> None:
    session = FakeSession(FakeResponse(404))
    with pytest.raises(TMDBError, match="nothing at"):
        client(session).show(1)
    assert len(session.calls) == 1


def test_a_401_is_reported_rather_than_retried() -> None:
    session = FakeSession(FakeResponse(401, payload={"status_message": "Invalid API key"}))
    with pytest.raises(TMDBError, match="401"):
        client(session).show(1)


def test_find_by_tvdb_returns_the_first_tv_result() -> None:
    session = FakeSession(FakeResponse(payload={"tv_results": [{"id": 1668}], "movie_results": []}))
    assert client(session).find_by_tvdb(79168) == {"id": 1668}


def test_find_by_tvdb_returns_none_when_tmdb_has_no_mapping() -> None:
    session = FakeSession(FakeResponse(payload={"tv_results": []}))
    assert client(session).find_by_tvdb(1) is None


def test_search_uses_the_right_year_parameter_per_kind() -> None:
    session = FakeSession(FakeResponse(payload={"results": []}), FakeResponse(payload={"results": []}))
    api = client(session)
    api.search("The Flash", kind=Kind.SHOW, year=2014)
    api.search("Arrival", kind=Kind.MOVIE, year=2016)
    assert session.calls[0][1]["first_air_date_year"] == 2014
    assert session.calls[1][1]["year"] == 2016


def test_a_show_payload_becomes_a_title() -> None:
    title = title_from_show(
        {
            "id": 1668,
            "name": "Friends",
            "first_air_date": "1994-09-22",
            "last_air_date": "2004-05-06",
            "status": "Ended",
            "number_of_episodes": 236,
            "episode_run_time": [22],
            "poster_path": "/p.jpg",
            "overview": "Six friends.",
            "external_ids": {"tvdb_id": 79168, "imdb_id": "tt0108778"},
        }
    )
    assert (title.name, title.year, title.tvdb_id, title.runtime) == ("Friends", 1994, 79168, 22)
    assert title.kind is Kind.SHOW
    assert title.total_episodes == 236


def test_a_movie_payload_becomes_a_title() -> None:
    title = title_from_movie({"id": 329865, "title": "Arrival", "release_date": "2016-11-10", "runtime": 116})
    assert (title.kind, title.year, title.runtime) == (Kind.MOVIE, 2016, 116)


def test_a_show_with_no_dates_yields_no_year() -> None:
    assert title_from_show({"id": 1, "name": "Untitled", "first_air_date": ""}).year is None


def test_episodes_without_numbering_are_dropped() -> None:
    episodes = episodes_from_season(
        {
            "episodes": [
                {"id": 1, "season_number": 1, "episode_number": 1, "name": "Pilot", "runtime": 22},
                {"id": 2, "season_number": 1, "episode_number": None},
            ]
        }
    )
    assert [(e.season_number, e.episode_number, e.name) for e in episodes] == [(1, 1, "Pilot")]
