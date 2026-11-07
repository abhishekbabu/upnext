"""The matching rules on their own, without a database.

`test_unmatched.py` covers the same rules through the store, which is where
their wiring can break; these pin the rules themselves.
"""

from __future__ import annotations

from upnext.domain.matching import CatalogEntry, match


def entries(*numbering: tuple[int, int]) -> list[CatalogEntry]:
    return [CatalogEntry(id=i, season_number=s, episode_number=e) for i, (s, e) in enumerate(numbering)]


def test_numbering_matches_exactly_and_never_nearby() -> None:
    catalog = entries((1, 1), (1, 2))
    assert match(catalog, unlinked={(1, 2), (1, 3)}, linked={}) == {(1, 2): 1}


def test_a_year_label_resolves_to_the_season_that_aired_then() -> None:
    catalog = [
        CatalogEntry(id=1, season_number=3, episode_number=1, air_date="2018-01-07"),
        CatalogEntry(id=2, season_number=4, episode_number=1, air_date="2019-01-06"),
    ]
    assert match(catalog, unlinked={(2019, 1)}, linked={}) == {(2019, 1): 2}


def test_a_year_label_never_resolves_to_specials() -> None:
    catalog = [
        CatalogEntry(id=1, season_number=0, episode_number=1, air_date="2019-02-01"),
        CatalogEntry(id=2, season_number=0, episode_number=2, air_date="2019-03-01"),
        CatalogEntry(id=3, season_number=1, episode_number=1, air_date="2019-04-01"),
    ]
    assert match(catalog, unlinked={(2019, 1)}, linked={}) == {(2019, 1): 3}


def test_a_split_run_maps_onto_a_flat_one_when_the_matches_agree() -> None:
    # Four episodes, flat at the catalog, split two-and-two at the source.
    catalog = entries((1, 1), (1, 2), (1, 3), (1, 4))
    assert match(catalog, unlinked={(2, 1), (2, 2)}, linked={(1, 1): 0, (1, 2): 1}) == {(2, 1): 2, (2, 2): 3}


def test_a_split_run_is_not_mapped_when_a_match_contradicts_the_ordering() -> None:
    catalog = entries((1, 1), (1, 2), (1, 3), (1, 4))
    assert match(catalog, unlinked={(2, 1), (2, 2)}, linked={(1, 1): 0, (1, 2): 3}) == {}


def test_a_split_run_is_not_mapped_from_a_partial_watch() -> None:
    # Without the whole run the source's season lengths are unknown.
    catalog = entries((1, 1), (1, 2), (1, 3), (1, 4))
    assert match(catalog, unlinked={(2, 1)}, linked={(1, 1): 0, (1, 2): 1}) == {}
