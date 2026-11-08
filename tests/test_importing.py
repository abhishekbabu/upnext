from __future__ import annotations

from pathlib import Path

import pytest

from upnext.adapters.outbound.importers.tvtime import TVTimeExport
from upnext.adapters.outbound.store.library import Library
from upnext.application.importing import import_export, summarize
from upnext.domain.errors import ExportError
from upnext.domain.models import Episode, ImportedTitle, Status, Title, TitleState, Watch


def test_an_export_round_trips_into_the_library(library: Library, export_dir: Path) -> None:
    summary = import_export(TVTimeExport(), library, export_dir)

    assert summary.titles == 5
    assert summary.watches == 4
    stats = library.stats()
    assert stats.watches == 4
    assert stats.by_status == {Status.WATCHING: 1, Status.WATCHLIST: 1, Status.COMPLETED: 1, Status.STOPPED: 2}


def test_importing_the_same_export_twice_converges(library: Library, export_dir: Path) -> None:
    import_export(TVTimeExport(), library, export_dir)
    second = import_export(TVTimeExport(), library, export_dir)

    assert second.titles == 5
    assert library.stats().watches == 4
    assert library.count_titles() == 5


def test_a_folder_that_is_not_an_export_is_refused(library: Library, tmp_path: Path) -> None:
    with pytest.raises(ExportError, match="is this a TV Time export?"):
        import_export(TVTimeExport(), library, tmp_path)


def test_the_summary_counts_statuses_in_enum_order() -> None:
    """Two runs of one import must print their statuses in the same order."""
    imported = [
        ImportedTitle(title=Title(name="Arrow"), state=TitleState(status=Status.STOPPED)),
        ImportedTitle(
            title=Title(name="Friends"),
            state=TitleState(status=Status.WATCHING),
            watches=[Watch(watched_at="2020-01-01 00:00:00", episode=(1, 1))],
        ),
    ]
    summary = summarize(imported)

    assert summary.watches == 1
    assert list(summary.by_status) == [Status.WATCHING, Status.STOPPED]


def test_a_status_with_nothing_in_it_is_left_out() -> None:
    summary = summarize([ImportedTitle(title=Title(name="Arrow"), state=TitleState(status=Status.STOPPED))])
    assert summary.by_status == {Status.STOPPED: 1}


def test_a_removed_title_is_not_imported_again(export_dir: Path, library: Library) -> None:
    import_export(TVTimeExport(), library, export_dir)
    beyblade = next(t for t in library.titles() if t.name == "Beyblade")
    library.conn.execute("DELETE FROM watches WHERE title_id = ?", (beyblade.id,))
    library.remove_title(beyblade.id, removed_at="2026-11-08T00:00:00+00:00")

    summary = import_export(TVTimeExport(), library, export_dir)

    assert "Beyblade" not in [t.name for t in library.titles()]
    assert summary.titles == len(library.titles())


def test_a_re_import_does_not_reopen_a_show_finished_since(export_dir: Path, library: Library) -> None:
    """TV Time still files it as followed; the catalog says it has ended and every episode is watched."""
    import_export(TVTimeExport(), library, export_dir)
    show = next(t for t in library.titles() if t.status is Status.WATCHING and t.unmatched_watched)
    numbers = library.conn.execute(
        "SELECT DISTINCT source_season, source_episode FROM watches WHERE title_id = ? AND source_season > 0",
        (show.id,),
    ).fetchall()
    library.replace_episodes(
        show.id, [Episode(season_number=s, episode_number=n) for s, n in numbers], keep_seasons=set()
    )
    library.link_watches(show.id)
    library.conn.execute("UPDATE titles SET air_status = 'Ended' WHERE id = ?", (show.id,))

    import_export(TVTimeExport(), library, export_dir)

    assert library.title(show.id).status is Status.COMPLETED
