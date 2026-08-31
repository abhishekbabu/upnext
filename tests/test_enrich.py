from __future__ import annotations

from upnext.catalog.enrich import enrich, enrich_title, resolve_show
from upnext.catalog.tmdb import TMDBError
from upnext.models import Status, Title, TitleState
from upnext.store.library import Library

SHOW_DETAIL = {
    "id": 1668,
    "name": "Friends",
    "first_air_date": "1994-09-22",
    "status": "Ended",
    "number_of_episodes": 236,
    "episode_run_time": [22],
    "external_ids": {"tvdb_id": 79168, "imdb_id": "tt0108778"},
    "seasons": [{"season_number": 0}, {"season_number": 1}],
}

SEASONS = {
    0: {"episodes": [{"id": 90, "season_number": 0, "episode_number": 1, "name": "Special"}]},
    1: {
        "episodes": [
            {"id": 1, "season_number": 1, "episode_number": 1, "name": "The One Where It Begins", "runtime": 22},
            {"id": 2, "season_number": 1, "episode_number": 2, "name": "The One With the Sonogram", "runtime": 22},
        ]
    },
}


class FakeTMDB:
    """Stands in for TMDBClient with the four methods enrichment calls."""

    def __init__(self, *, found: dict | None = None, search_results: list | None = None, missing_seasons=()) -> None:
        self.found = found
        self.search_results = search_results or []
        self.missing_seasons = set(missing_seasons)
        self.searched: list[str] = []

    def find_by_tvdb(self, tvdb_id: int) -> dict | None:
        return self.found

    def search(self, name: str, *, kind=None, year=None) -> list:
        self.searched.append(name)
        return self.search_results

    def show(self, tmdb_id: int) -> dict:
        return SHOW_DETAIL

    def season(self, tmdb_id: int, season_number: int) -> dict:
        if season_number in self.missing_seasons:
            raise TMDBError("gone")
        return SEASONS[season_number]


def imported(library: Library, **kwargs):
    title_id = library.upsert_title(Title(name=kwargs.pop("name", "Friends"), **kwargs))
    library.set_state(title_id, TitleState(status=Status.WATCHING))
    return library.title(title_id)


def test_a_tvdb_id_resolves_without_searching(library: Library) -> None:
    client = FakeTMDB(found={"id": 1668})
    assert resolve_show(client, imported(library, tvdb_id=79168)) == {"id": 1668}
    assert client.searched == []


def test_search_is_the_fallback_when_tmdb_has_no_tvdb_mapping(library: Library) -> None:
    client = FakeTMDB(found=None, search_results=[{"id": 1668, "first_air_date": "1994-09-22"}])
    assert resolve_show(client, imported(library, tvdb_id=1, year=1994))["id"] == 1668
    assert client.searched == ["Friends"]


def test_a_search_hit_from_the_wrong_year_is_refused(library: Library) -> None:
    client = FakeTMDB(found=None, search_results=[{"id": 9, "first_air_date": "2018-01-01"}])
    assert resolve_show(client, imported(library, tvdb_id=1, year=1994)) is None


def test_a_known_tmdb_id_short_circuits_resolution(library: Library) -> None:
    client = FakeTMDB(found=None)
    assert resolve_show(client, imported(library, tmdb_id=1668)) == {"id": 1668}


def test_enrichment_fills_the_title_and_every_episode(library: Library) -> None:
    title = imported(library, tvdb_id=79168)
    assert enrich_title(FakeTMDB(found={"id": 1668}), library, title) is True

    row = library.title(title.id)
    assert (row.tmdb_id, row.air_status, row.total_episodes) == (1668, "Ended", 236)
    episodes = library.episodes(title.id)
    assert [(e["season_number"], e["episode_number"]) for e in episodes] == [(0, 1), (1, 1), (1, 2)]
    assert episodes[1]["name"] == "The One Where It Begins"
    assert library.needing_enrichment() == []


def test_enrichment_keeps_the_watches_recorded_before_it(library: Library) -> None:
    from upnext.models import Watch

    title = imported(library, tvdb_id=79168)
    library.record_watch(title.id, Watch(watched_at="2018-05-12 01:10:14", episode=(1, 1), source="tvtime"))
    enrich_title(FakeTMDB(found={"id": 1668}), library, title)

    assert library.title(title.id).episodes_watched == 1
    # The placeholder the import created is the row TMDB filled in, not a second one.
    assert len(library.episodes(title.id)) == 3


def test_a_season_tmdb_cannot_serve_does_not_abandon_the_show(library: Library) -> None:
    title = imported(library, tvdb_id=79168)
    assert enrich_title(FakeTMDB(found={"id": 1668}, missing_seasons=[0]), library, title) is True
    assert [(e["season_number"], e["episode_number"]) for e in library.episodes(title.id)] == [(1, 1), (1, 2)]


def test_an_unmatched_title_is_reported_and_left_alone(library: Library) -> None:
    title = imported(library, tvdb_id=1)
    result = enrich(FakeTMDB(found=None), library, [title])
    assert (result.matched, result.unmatched, result.total) == ([], ["Friends"], 1)
    assert library.needing_enrichment()[0].id == title.id


def test_a_tmdb_failure_counts_as_unmatched_rather_than_crashing(library: Library) -> None:
    class Broken(FakeTMDB):
        def find_by_tvdb(self, tvdb_id: int):
            raise TMDBError("boom")

    result = enrich(Broken(), library, [imported(library, tvdb_id=1)])
    assert result.unmatched == ["Friends"]


def test_progress_is_reported_per_title(library: Library) -> None:
    seen = []
    enrich(
        FakeTMDB(found={"id": 1668}),
        library,
        [imported(library, tvdb_id=79168)],
        on_progress=lambda t, ok: seen.append((t.name, ok)),
    )
    assert seen == [("Friends", True)]
