"""Turn an export into a library.

The whole use case is offline: a source reads a folder, and the three writes
below record what it found. This is the layer that decides an import is one
unit of work, which is why the commit is here and not in the repository.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from upnext.domain.models import ImportedTitle, Status, in_status_order
from upnext.domain.ports import ImportSource, WatchLibrary


@dataclass(slots=True)
class ImportSummary:
    """What an import did, for an inbound adapter to render."""

    titles: int = 0
    watches: int = 0
    by_status: dict[Status, int] = field(default_factory=dict)


def summarize(imported: list[ImportedTitle]) -> ImportSummary:
    counts = Counter(item.state.status for item in imported)
    return ImportSummary(
        titles=len(imported),
        watches=sum(len(item.watches) for item in imported),
        by_status=in_status_order(counts),
    )


def import_export(source: ImportSource, library: WatchLibrary, export_dir: Path) -> ImportSummary:
    """Read an export and write all of it, returning what the export holds.

    What it holds, not what changed: a re-import writes nothing and reports
    the same figures. Titles removed from the library are left out of both.

    Raises:
        ExportError: the folder is not an export this source recognises.
    """
    # A title removed from the library stays removed, though the export lists it.
    imported = [item for item in source.read(export_dir) if not library.was_removed(item.title)]
    for item in imported:
        title_id = library.upsert_title(item.title)
        library.set_state(title_id, item.state)
        for watch in item.watches:
            library.record_watch(title_id, watch)
    library.commit()
    return summarize(imported)
