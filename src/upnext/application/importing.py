"""Turn an export into a library.

The whole use case is offline: a source reads a folder, and the three writes
below record what it found. This is the layer that decides an import is one
unit of work, which is why the commit is here and not in the repository.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from upnext.domain.models import ImportedTitle, Status
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
        # Ordered by the enum rather than by count, so two runs of the same
        # import print their statuses in the same order.
        by_status={status: counts[status] for status in Status if counts[status]},
    )


def import_export(source: ImportSource, library: WatchLibrary, export_dir: Path) -> ImportSummary:
    """Read an export and write all of it, returning what was written.

    Raises:
        ExportError: the folder is not an export this source recognises.
    """
    imported = source.read(export_dir)
    for item in imported:
        title_id = library.upsert_title(item.title)
        library.set_state(title_id, item.state)
        for watch in item.watches:
            library.record_watch(title_id, watch)
    library.commit()
    return summarize(imported)
