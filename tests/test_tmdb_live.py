"""The one test that talks to TMDB. Opt in with `just test-integration`.

Everything else about enrichment is covered against fakes; this exists to catch
the thing fakes cannot — TMDB changing the shape of what it returns.
"""

from __future__ import annotations

import pytest

from upnext.catalog.tmdb import TMDBClient, title_from_show
from upnext.settings import load_settings

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

    title = title_from_show(client.show(found["id"]))
    assert title.name == "Friends"
    assert title.year == 1994
    assert title.tvdb_id == 79168
    assert title.total_episodes == 236


def test_a_season_comes_back_with_numbered_episodes(client: TMDBClient) -> None:
    from upnext.catalog.tmdb import episodes_from_season

    episodes = episodes_from_season(client.season(1668, 1))
    assert len(episodes) == 24
    assert episodes[0].episode_number == 1
