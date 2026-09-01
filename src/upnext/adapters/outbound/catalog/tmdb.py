"""A small TMDB client — the source of truth for what a title actually is.

TMDB rather than IMDb because IMDb has no free public API, and rather than
TheTVDB because TVDB v4 gates most of its data behind a subscriber PIN. Its
/find endpoint maps a TheTVDB id straight to a TMDB one, which is what makes
enrichment an identity lookup rather than a name search.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from upnext.domain.errors import CatalogError, ConfigurationError, RetryableCatalogError
from upnext.domain.models import Episode, Kind, Title
from upnext.domain.ports import CatalogMatch, CatalogShow

BASE_URL = "https://api.themoviedb.org/3"
TIMEOUT_SECONDS = 15


class TMDBClient:
    """The `Catalog` port, over TMDB's v3 API.

    Synchronous, rate-limited, and deliberately narrow: only the endpoints
    enrichment needs are exposed, and anything the app grows into should be
    added here rather than by passing raw paths around. Nothing outside this
    module sees a TMDB payload — the port's methods translate on the way out.
    """

    def __init__(
        self,
        api_key: str,
        *,
        language: str = "en-US",
        min_interval_seconds: float = 0.05,
        session: requests.Session | None = None,
    ) -> None:
        if not api_key:
            raise ConfigurationError("No TMDB API key. Set UPNEXT_TMDB_API_KEY (see .env.template).")
        self.api_key = api_key
        self.language = language
        self.min_interval = min_interval_seconds
        self.session = session or requests.Session()
        self._lock = threading.Lock()
        self._last_call = 0.0

    # ------------------------------------------------------------- transport

    def _throttle(self) -> None:
        with self._lock:
            elapsed = time.monotonic() - self._last_call
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self._last_call = time.monotonic()

    @retry(
        retry=retry_if_exception_type(RetryableCatalogError),
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=0.5, max=8),
        reraise=True,
    )
    def get(self, path: str, **params: Any) -> dict:
        self._throttle()
        query = {"api_key": self.api_key, "language": self.language, **params}
        try:
            response = self.session.get(f"{BASE_URL}{path}", params=query, timeout=TIMEOUT_SECONDS)
        except (requests.Timeout, requests.ConnectionError) as exc:
            raise RetryableCatalogError(str(exc)) from exc

        if response.status_code == 429:
            # TMDB's own guidance is to honour Retry-After; sleeping here keeps
            # the backoff in one place rather than splitting it with tenacity.
            time.sleep(float(response.headers.get("Retry-After", "1")))
            raise RetryableCatalogError("rate limited")
        if response.status_code >= 500:
            raise RetryableCatalogError(f"TMDB {response.status_code} for {path}")
        if response.status_code == 404:
            raise CatalogError(f"TMDB has nothing at {path}")
        if not response.ok:
            raise CatalogError(f"TMDB {response.status_code} for {path}: {response.text[:200]}")
        return response.json()

    # ------------------------------------------------------------- endpoints

    def find_by_tvdb(self, tvdb_id: int) -> CatalogMatch | None:
        results = self.get("/find/" + str(tvdb_id), external_source="tvdb_id").get("tv_results") or []
        return _match(results[0]) if results else None

    def search_shows(self, name: str, *, year: int | None = None) -> list[CatalogMatch]:
        params: dict[str, Any] = {"query": name}
        if year is not None:
            params["first_air_date_year"] = year
        return [_match(item) for item in self.get("/search/tv", **params).get("results") or []]

    def fetch_show(self, catalog_id: int) -> CatalogShow:
        """The show and every episode of every season TMDB will serve.

        A season listed on the show but missing its own endpoint is a TMDB data
        gap, not a reason to abandon the rest of the show — the walk is here
        rather than in the caller because it is a fact about this API, not a
        decision about enrichment.
        """
        detail = self.show(catalog_id)
        episodes: list[Episode] = []
        for season in detail.get("seasons") or []:
            number = season.get("season_number")
            if number is None:
                continue
            try:
                payload = self.season(catalog_id, int(number))
            except CatalogError:
                continue
            episodes.extend(episodes_from_season(payload))
        return CatalogShow(title=title_from_show(detail), episodes=episodes)

    # ------------------------------------------------------------ raw payloads

    def show(self, tmdb_id: int) -> dict:
        return self.get(f"/tv/{tmdb_id}", append_to_response="external_ids")

    def season(self, tmdb_id: int, season_number: int) -> dict:
        return self.get(f"/tv/{tmdb_id}/season/{season_number}")

    def movie(self, tmdb_id: int) -> dict:
        return self.get(f"/movie/{tmdb_id}", append_to_response="external_ids")

    def search(self, name: str, *, kind: Kind = Kind.SHOW, year: int | None = None) -> list[dict]:
        """Raw search, for films — which have no port method until they have an importer."""
        path = "/search/tv" if kind is Kind.SHOW else "/search/movie"
        params: dict[str, Any] = {"query": name}
        if year is not None:
            params["first_air_date_year" if kind is Kind.SHOW else "year"] = year
        return self.get(path, **params).get("results") or []


# --------------------------------------------------------------- translation


def title_from_show(payload: dict) -> Title:
    return Title(
        name=payload.get("name") or payload.get("original_name") or "",
        kind=Kind.SHOW,
        year=_year(payload.get("first_air_date")),
        tmdb_id=payload.get("id"),
        tvdb_id=(payload.get("external_ids") or {}).get("tvdb_id"),
        imdb_id=(payload.get("external_ids") or {}).get("imdb_id"),
        overview=payload.get("overview") or None,
        poster_path=payload.get("poster_path"),
        backdrop_path=payload.get("backdrop_path"),
        air_status=payload.get("status"),
        first_air_date=payload.get("first_air_date") or None,
        last_air_date=payload.get("last_air_date") or None,
        total_episodes=payload.get("number_of_episodes"),
        runtime=_first(payload.get("episode_run_time")),
    )


def title_from_movie(payload: dict) -> Title:
    return Title(
        name=payload.get("title") or payload.get("original_title") or "",
        kind=Kind.MOVIE,
        year=_year(payload.get("release_date")),
        tmdb_id=payload.get("id"),
        imdb_id=payload.get("imdb_id") or (payload.get("external_ids") or {}).get("imdb_id"),
        overview=payload.get("overview") or None,
        poster_path=payload.get("poster_path"),
        backdrop_path=payload.get("backdrop_path"),
        air_status=payload.get("status"),
        first_air_date=payload.get("release_date") or None,
        runtime=payload.get("runtime"),
    )


def episodes_from_season(payload: dict) -> list[Episode]:
    return [
        Episode(
            season_number=item["season_number"],
            episode_number=item["episode_number"],
            name=item.get("name") or None,
            overview=item.get("overview") or None,
            air_date=item.get("air_date") or None,
            runtime=item.get("runtime"),
            still_path=item.get("still_path"),
            tmdb_id=item.get("id"),
        )
        for item in payload.get("episodes") or []
        if item.get("season_number") is not None and item.get("episode_number") is not None
    ]


def _match(payload: dict) -> CatalogMatch:
    return CatalogMatch(
        catalog_id=int(payload["id"]),
        name=payload.get("name") or payload.get("original_name") or "",
        year=_year(payload.get("first_air_date")),
    )


def _year(date: str | None) -> int | None:
    return int(date[:4]) if date and len(date) >= 4 and date[:4].isdigit() else None


def _first(values: list | None) -> int | None:
    return values[0] if values else None
