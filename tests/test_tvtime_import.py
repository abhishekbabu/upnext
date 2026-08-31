from __future__ import annotations

from pathlib import Path

import pytest

from upnext.adapters.outbound.importers.tvtime import read_export
from upnext.domain.errors import ExportError
from upnext.domain.models import Status


def by_name(export_dir: Path) -> dict:
    return {item.title.name: item for item in read_export(export_dir)}


def test_rejects_a_folder_that_is_not_an_export(tmp_path: Path) -> None:
    with pytest.raises(ExportError, match="missing"):
        read_export(tmp_path)


def test_rejects_a_path_that_is_not_a_directory(tmp_path: Path) -> None:
    file = tmp_path / "export.zip"
    file.write_text("")
    with pytest.raises(ExportError, match="not a directory"):
        read_export(file)


def test_statuses_come_from_active_and_archived(export_dir: Path) -> None:
    items = by_name(export_dir)
    assert items["Friends"].state.status is Status.WATCHING
    # Archived while still followed is TV Time's "I have finished this".
    assert items["Arrow"].state.status is Status.COMPLETED
    assert items["Beyblade"].state.status is Status.STOPPED
    assert items["The Ultimate Fighter"].state.status is Status.WATCHLIST


def test_a_show_known_only_from_its_seen_count_is_still_imported(export_dir: Path) -> None:
    flash = by_name(export_dir)["The Flash"]
    assert flash.title.year == 2014
    assert flash.state.reported_watched == 5
    assert flash.watches == []


def test_watches_carry_episode_numbers_and_rewatch_flags(export_dir: Path) -> None:
    friends = by_name(export_dir)["Friends"]
    assert [(w.episode, w.is_rewatch) for w in friends.watches] == [
        ((1, 1), False),
        ((1, 2), False),
        ((1, 1), True),
    ]


def test_non_watch_tracking_rows_are_ignored(export_dir: Path) -> None:
    assert len(by_name(export_dir)["Arrow"].watches) == 1


def test_favorites_and_ratings_transfer(export_dir: Path) -> None:
    friends = by_name(export_dir)["Friends"]
    assert friends.state.is_favorite is True
    # TV Time rates out of five; upnext keeps a ten-point scale.
    assert friends.state.rating == 10
    assert friends.state.followed_at == "2017-03-07 05:25:05"
    assert by_name(export_dir)["Arrow"].state.is_favorite is False


def test_tvdb_ids_are_preserved_for_enrichment(export_dir: Path) -> None:
    assert by_name(export_dir)["Friends"].title.tvdb_id == 79168


def test_a_non_year_parenthetical_is_left_in_the_name(export_dir: Path, write_csv) -> None:
    write_csv(
        export_dir / "user_tv_show_data.csv",
        ["nb_episodes_seen", "tv_show_name", "user_id", "tv_show_id", "is_followed", "is_favorited"],
        [
            {
                "nb_episodes_seen": "295",
                "tv_show_name": "Whose Line Is It Anyway? (US)",
                "user_id": "1",
                "tv_show_id": "73387",
                "is_followed": "1",
                "is_favorited": "0",
            }
        ],
    )
    names = {item.title.name: item.title.year for item in read_export(export_dir)}
    assert names["Whose Line Is It Anyway? (US)"] is None


def test_a_watch_with_no_episode_number_is_kept_against_the_show(export_dir: Path, write_csv, watch_row) -> None:
    """TV Time exports some shows with episode_number 0 — Beyblade's whole run."""
    write_csv(
        export_dir / "tracking-prod-records-v2.csv",
        ["user_id", "created_at", "s_id", "ep_id", "gsi", "key", "series_name", "season_number", "episode_number"],
        [
            watch_row("2019-01-01 00:00:00", "70799", "4149573", "watch-episode-1", "Beyblade", 5, 0),
            watch_row("2019-01-02 00:00:00", "70799", "4149611", "watch-episode-2", "Beyblade", 5, 0),
        ],
    )
    beyblade = by_name(export_dir)["Beyblade"]
    assert [w.episode for w in beyblade.watches] == [None, None]
    assert len(beyblade.watches) == 2
