from __future__ import annotations

from pathlib import Path

import pytest

from upnext.adapters.inbound.cli import commands as cli
from upnext.adapters.outbound.store.db import connect, open_library
from upnext.adapters.outbound.store.library import Library
from upnext.domain.models import Episode, Title


def test_import_ingests_an_export_and_reports_what_it_did(export_dir: Path, tmp_path: Path, capsys) -> None:
    db = tmp_path / "library.db"
    assert cli.main(["--db", str(db), "import", str(export_dir)]) == 0

    out = capsys.readouterr().out
    assert "Imported 5 titles and 4 watches" in out
    assert "watching   1" in out
    with open_library(db) as conn:
        assert Library(conn).stats()["watches"] == 4


def test_import_of_a_folder_that_is_not_an_export_fails_cleanly(tmp_path: Path, capsys) -> None:
    assert cli.main(["--db", str(tmp_path / "l.db"), "import", str(tmp_path)]) == 2
    assert "is this a TV Time export?" in capsys.readouterr().err


def test_stats_summarises_an_imported_library(export_dir: Path, tmp_path: Path, capsys) -> None:
    db = tmp_path / "library.db"
    cli.main(["--db", str(db), "import", str(export_dir)])
    capsys.readouterr()

    assert cli.main(["--db", str(db), "stats"]) == 0
    out = capsys.readouterr().out
    # Three distinct episodes from four watches — the fourth is a rewatch.
    assert "3 episodes across 2 titles" in out
    assert "from 2018-05-12 to 2021-04-23" in out


def test_enrich_without_a_key_explains_itself_rather_than_calling_tmdb(
    export_dir: Path, tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("UPNEXT_TMDB_API_KEY", "")
    db = tmp_path / "library.db"
    cli.main(["--db", str(db), "import", str(export_dir)])
    capsys.readouterr()

    assert cli.main(["--db", str(db), "enrich"]) == 2
    assert "No TMDB API key" in capsys.readouterr().err


def test_enrich_on_an_empty_library_says_to_import_first(tmp_path: Path, capsys) -> None:
    """An empty library and a fully enriched one both have nothing pending.

    Reporting them identically sends someone hunting for a broken API key when
    what they need is `upnext import`.
    """
    db = tmp_path / "library.db"
    connect(db).close()
    assert cli.main(["--db", str(db), "enrich"]) == 0
    assert "the library is empty" in capsys.readouterr().out


def test_enrich_on_an_already_enriched_library_does_nothing(export_dir: Path, tmp_path: Path, capsys) -> None:
    db = tmp_path / "library.db"
    cli.main(["--db", str(db), "import", str(export_dir)])
    with open_library(db) as conn:
        library = Library(conn)
        for title in library.needing_enrichment():
            library.apply_enrichment(title.id, Title(name=title.name), enriched_at="2026-01-01T00:00:00+00:00")
    capsys.readouterr()

    assert cli.main(["--db", str(db), "enrich"]) == 0
    assert "every title already has catalog data" in capsys.readouterr().out


def test_an_unknown_import_source_is_refused(export_dir: Path, tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        cli.main(["--db", str(tmp_path / "l.db"), "import", str(export_dir), "--source", "letterboxd"])


def test_enrich_walks_the_pending_titles(export_dir: Path, tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("UPNEXT_TMDB_API_KEY", "key")
    db = tmp_path / "library.db"
    cli.main(["--db", str(db), "import", str(export_dir)])
    capsys.readouterr()

    calls: list = []

    def fake_enrich(catalog, library, titles, on_progress=None):
        titles = list(titles)
        calls.append(titles)
        for title in titles:
            on_progress(title, title.name == "Arrow")
        from upnext.application.enrichment import EnrichmentResult

        return EnrichmentResult(
            matched=[t.name for t in titles if t.name == "Arrow"],
            unmatched=[t.name for t in titles if t.name != "Arrow"],
        )

    monkeypatch.setattr(cli, "enrich", fake_enrich)
    assert cli.main(["--db", str(db), "enrich", "--limit", "2"]) == 0

    out = capsys.readouterr().out
    assert len(calls[0]) == 2
    assert "Matched 1 of 2." in out
    assert "Not found on TMDB" in out


def test_a_missing_subcommand_is_rejected() -> None:
    with pytest.raises(SystemExit):
        cli.main([])


def test_serve_hands_off_to_uvicorn(monkeypatch) -> None:
    seen = {}
    monkeypatch.setattr("uvicorn.run", lambda app, host, port: seen.update(app=app, host=host, port=port))
    assert cli.main(["serve", "--port", "9999"]) == 0
    assert seen == {"app": "upnext.adapters.inbound.web.api:app", "host": "127.0.0.1", "port": 9999}


def test_relink_matches_watches_against_episodes_already_stored(export_dir: Path, tmp_path: Path, capsys) -> None:
    """Enrichment links as it goes, but only titles it enriches.

    A library already sitting on a full episode list would otherwise never pick
    up an improvement to how matching works.
    """
    db = tmp_path / "library.db"
    cli.main(["--db", str(db), "import", str(export_dir)])
    with open_library(db) as conn:
        library = Library(conn)
        friends = next(row for row in library.titles() if row.name == "Friends")
        library.apply_enrichment(
            friends.id, Title(name="Friends", total_episodes=2), enriched_at="2026-01-01T00:00:00+00:00"
        )
        for number in (1, 2):
            library.upsert_episode(friends.id, Episode(season_number=1, episode_number=number))
    capsys.readouterr()

    assert cli.main(["--db", str(db), "relink"]) == 0
    out = capsys.readouterr().out
    assert "Matched 3 more watches" in out
    with open_library(db) as conn:
        assert next(r for r in Library(conn).titles() if r.name == "Friends").episodes_watched == 2


def test_relink_names_the_titles_tmdb_cannot_account_for(export_dir: Path, tmp_path: Path, capsys) -> None:
    db = tmp_path / "library.db"
    cli.main(["--db", str(db), "import", str(export_dir)])
    with open_library(db) as conn:
        library = Library(conn)
        arrow = next(row for row in library.titles() if row.name == "Arrow")
        library.apply_enrichment(
            arrow.id, Title(name="Arrow", total_episodes=1), enriched_at="2026-01-01T00:00:00+00:00"
        )
        library.upsert_episode(arrow.id, Episode(season_number=1, episode_number=1))
    capsys.readouterr()

    cli.main(["--db", str(db), "relink"])
    # Arrow's watch is of 3x13, which the one-episode list has no place for.
    assert "Arrow" in capsys.readouterr().out


def test_relink_on_a_library_with_nothing_left_over_says_so(tmp_path: Path, capsys) -> None:
    db = tmp_path / "library.db"
    connect(db).close()
    assert cli.main(["--db", str(db), "relink"]) == 0
    assert "Every watch is accounted for" in capsys.readouterr().out
