from __future__ import annotations

from conftest import FakeCatalog

from upnext.adapters.outbound.store.library import Library
from upnext.application.enrichment import enrich, enrich_title, resolve_show
from upnext.domain.errors import CatalogError
from upnext.domain.models import Status, Title, TitleState
from upnext.domain.ports import CatalogMatch


def imported(library: Library, **kwargs):
    title_id = library.upsert_title(Title(name=kwargs.pop("name", "Friends"), **kwargs))
    library.set_state(title_id, TitleState(status=Status.WATCHING))
    return library.title(title_id)


def test_a_tvdb_id_resolves_without_searching(library: Library) -> None:
    catalog = FakeCatalog(found=CatalogMatch(catalog_id=1668))
    assert resolve_show(catalog, imported(library, tvdb_id=79168)).catalog_id == 1668
    assert catalog.searched == []


def test_search_is_the_fallback_when_the_catalog_has_no_tvdb_mapping(library: Library) -> None:
    catalog = FakeCatalog(found=None, search_results=[CatalogMatch(catalog_id=1668, year=1994)])
    assert resolve_show(catalog, imported(library, tvdb_id=1, year=1994)).catalog_id == 1668
    assert catalog.searched == ["Friends"]


def test_a_search_hit_from_the_wrong_year_is_refused(library: Library) -> None:
    catalog = FakeCatalog(found=None, search_results=[CatalogMatch(catalog_id=9, year=2018)])
    assert resolve_show(catalog, imported(library, tvdb_id=1, year=1994)) is None


def test_a_candidate_the_catalog_cannot_date_is_still_allowed(library: Library) -> None:
    """An unknown year is not a disagreement — refusing it would lose real matches."""
    catalog = FakeCatalog(found=None, search_results=[CatalogMatch(catalog_id=7, year=None)])
    assert resolve_show(catalog, imported(library, tvdb_id=1, year=1994)).catalog_id == 7


def test_a_known_tmdb_id_short_circuits_resolution(library: Library) -> None:
    catalog = FakeCatalog(found=None)
    assert resolve_show(catalog, imported(library, tmdb_id=1668)).catalog_id == 1668
    assert catalog.searched == []


def test_enrichment_fills_the_title_and_every_episode(library: Library) -> None:
    title = imported(library, tvdb_id=79168)
    assert enrich_title(FakeCatalog(found=CatalogMatch(catalog_id=1668)), library, title) is True

    row = library.title(title.id)
    assert (row.tmdb_id, row.air_status, row.total_episodes) == (1668, "Ended", 236)
    episodes = library.episodes(title.id)
    assert [(e.season_number, e.episode_number) for e in episodes] == [(0, 1), (1, 1), (1, 2)]
    assert episodes[1].name == "The One Where It Begins"
    assert library.needing_enrichment() == []


def test_enrichment_keeps_the_watches_recorded_before_it(library: Library) -> None:
    from upnext.domain.models import Watch

    title = imported(library, tvdb_id=79168)
    library.record_watch(title.id, Watch(watched_at="2018-05-12 01:10:14", episode=(1, 1), source="tvtime"))
    enrich_title(FakeCatalog(found=CatalogMatch(catalog_id=1668)), library, title)

    assert library.title(title.id).episodes_watched == 1
    # The placeholder the import created is the row TMDB filled in, not a second one.
    assert len(library.episodes(title.id)) == 3


def test_an_unmatched_title_is_reported_and_left_alone(library: Library) -> None:
    title = imported(library, tvdb_id=1)
    result = enrich(FakeCatalog(found=None), library, [title])
    assert (result.matched, result.unmatched, result.total) == ([], ["Friends"], 1)
    assert library.needing_enrichment()[0].id == title.id


def test_a_catalog_failure_counts_as_unmatched_rather_than_crashing(library: Library) -> None:
    class Broken(FakeCatalog):
        def find_by_tvdb(self, tvdb_id: int):
            raise CatalogError("boom")

    result = enrich(Broken(), library, [imported(library, tvdb_id=1)])
    assert result.unmatched == ["Friends"]
    # Nothing was stamped, so the next run picks it up again.
    assert len(library.needing_enrichment()) == 1


def test_progress_is_reported_per_title(library: Library) -> None:
    seen = []
    enrich(
        FakeCatalog(found=CatalogMatch(catalog_id=1668)),
        library,
        [imported(library, tvdb_id=79168)],
        on_progress=lambda t, ok: seen.append((t.name, ok)),
    )
    assert seen == [("Friends", True)]
