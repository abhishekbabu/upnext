from __future__ import annotations

import pytest

from upnext import bootstrap
from upnext.adapters.outbound.catalog.tmdb import TMDBClient
from upnext.config.settings import Settings
from upnext.domain.errors import ConfigurationError


def test_the_catalog_is_built_from_settings() -> None:
    catalog = bootstrap.build_catalog(Settings(tmdb_api_key="key", tmdb_language="fr-FR"))
    assert isinstance(catalog, TMDBClient)
    assert catalog.language == "fr-FR"


def test_building_a_catalog_without_a_key_says_what_to_set() -> None:
    """Raised before a single title is read: failing partway through is worse."""
    with pytest.raises(ConfigurationError, match="UPNEXT_TMDB_API_KEY"):
        bootstrap.build_catalog(Settings(tmdb_api_key=""))


def test_the_default_import_source_is_registered() -> None:
    source = bootstrap.import_source(bootstrap.DEFAULT_IMPORT_SOURCE)
    assert source.name == "tvtime"


def test_an_unknown_import_source_names_the_ones_that_exist() -> None:
    with pytest.raises(ConfigurationError, match="Available: tvtime"):
        bootstrap.import_source("letterboxd")
