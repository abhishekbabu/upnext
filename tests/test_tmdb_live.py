"""The one test that talks to TMDB. Opt in with `just test-integration`.

Everything else about enrichment is covered against fakes; this exists to catch
the thing fakes cannot — TMDB changing the shape of what it returns. It runs
through the `Catalog` port, so it also checks that the translation from TMDB's
JSON to the domain still holds.
"""

from __future__ import annotations

import pytest

from upnext.adapters.outbound.catalog.tmdb import TMDBClient
from upnext.config.settings import load_settings

pytestmark = pytest.mark.integration


@pytest.fixture
def client() -> TMDBClient:
    settings = load_settings()
    if not settings.tmdb_api_key:
        pytest.skip("UPNEXT_TMDB_API_KEY is not set")
    return TMDBClient(settings.tmdb_api_key, language=settings.tmdb_language)


def test_a_tvdb_id_from_the_export_resolves_to_the_right_show(client: TMDBClient) -> None:
    # 79168 is Friends' TheTVDB id, exactly as a TV Time export carries it.
    found = client.find_by_tvdb(79168)
    assert found is not None
    assert (found.catalog_id, found.name, found.year) == (1668, "Friends", 1994)


def test_fetching_a_show_brings_back_its_episodes(client: TMDBClient) -> None:
    show = client.fetch_show(1668)

    assert show.title.name == "Friends"
    assert show.title.year == 1994
    assert show.title.tvdb_id == 79168
    # Not an exact count: TMDB excludes specials and counts each double-length
    # episode once, and revises both as contributors edit. The field being a
    # plausible whole-series number is the shape check; 236 was not.
    assert show.title.total_episodes is not None
    assert show.title.total_episodes > 200

    # Season 0 is carried through, so specials the user logged keep their rows.
    seasons = {episode.season_number for episode in show.episodes}
    assert seasons >= {0, 1, 10}
    assert len(show.episodes) > 200
