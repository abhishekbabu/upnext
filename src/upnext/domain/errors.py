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
    """The catalog refused a request in a way that retrying will not fix."""


class RetryableCatalogError(UpnextError):
    """A timeout, a connection failure or a 5xx — worth another attempt.

    Never escapes an adapter: the retry policy that catches it lives there, and
    what reaches the application is either a result or a `CatalogError`.
    """
