"""Every failure upnext raises deliberately.

Errors live in the domain rather than beside the code that raises them, so a
caller can catch what went wrong without importing the adapter it went wrong
in. Nothing signals failure by return value: `None` and `[]` are answers, and a
caller cannot tell them from a request that never happened.

Only `adapters/inbound/` turns one of these into something a human reads.
"""

from __future__ import annotations


class UpnextError(Exception):
    """Base for everything upnext raises on purpose."""


class ConfigurationError(UpnextError):
    """The machine is not set up for what was asked — a missing key, usually.

    Separate from the failures below because it is answerable: the message says
    what to put where, and no amount of retrying substitutes for it.
    """


class ExportError(UpnextError):
    """The folder given is not a usable export."""


class CatalogError(UpnextError):
    """The catalog could not answer for one title."""


class LibraryError(UpnextError):
    """The library file cannot be opened as one: a directory, or not SQLite."""


class DuplicateTitleError(UpnextError):
    """Two titles in the library are one title at the catalog.

    Not a catalog failure: nothing went wrong at TMDB, and the next run will
    find the same thing. Merging them is a person's call — `upnext move`.
    """


class RemovalError(UpnextError):
    """A title with viewings cannot be removed: that would delete history. Stop it instead."""


class NotFoundError(UpnextError):
    """Something was asked for by an id the library does not have."""


class RetryableCatalogError(CatalogError):
    """A timeout, a connection failure or a 5xx — worth another attempt.

    The adapter retries it. Once the attempts run out it reaches the caller
    as what it is — a `CatalogError` — so the application needs no case for it.
    """
