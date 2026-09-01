"""The composition root: the one module that names concrete implementations.

Everything else works against ports, so another catalog or another importer is
an entry here and a change to nothing else.
"""

from __future__ import annotations

from upnext.adapters.outbound.catalog.tmdb import TMDBClient
from upnext.adapters.outbound.importers.tvtime import TVTimeExport
from upnext.config.settings import Settings
from upnext.domain.errors import ConfigurationError
from upnext.domain.ports import Catalog, ImportSource

IMPORT_SOURCES: dict[str, ImportSource] = {source.name: source for source in (TVTimeExport(),)}

DEFAULT_IMPORT_SOURCE = TVTimeExport.name


def build_catalog(settings: Settings) -> Catalog:
    """The catalog upnext resolves titles against.

    Raises:
        ConfigurationError: no API key — raised here, before any title is read,
            because failing partway through an enrichment run is worse than
            not starting one.
    """
    return TMDBClient(
        settings.tmdb_api_key,
        language=settings.tmdb_language,
        min_interval_seconds=settings.tmdb_min_interval_seconds,
    )


def import_source(name: str) -> ImportSource:
    """The importer for an export from `name`.

    Raises:
        ConfigurationError: no importer by that name.
    """
    try:
        return IMPORT_SOURCES[name]
    except KeyError:
        known = ", ".join(sorted(IMPORT_SOURCES))
        raise ConfigurationError(f"No importer for {name!r}. Available: {known}.") from None
