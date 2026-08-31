from __future__ import annotations

from pathlib import Path

import pytest

from upnext import cli
from upnext.store.db import connect, open_library
from upnext.store.library import Library


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


def test_enrich_on_an_already_enriched_library_does_nothing(tmp_path: Path, capsys) -> None:
    db = tmp_path / "library.db"
    connect(db).close()
    assert cli.main(["--db", str(db), "enrich"]) == 0
    assert "Nothing to enrich" in capsys.readouterr().out


def test_enrich_walks_the_pending_titles(export_dir: Path, tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("UPNEXT_TMDB_API_KEY", "key")
    db = tmp_path / "library.db"
    cli.main(["--db", str(db), "import", str(export_dir)])
    capsys.readouterr()

    calls: list = []

    def fake_enrich(client, library, titles, on_progress=None):
        titles = list(titles)
        calls.append(titles)
        for title in titles:
            on_progress(title, title.name == "Arrow")
        from upnext.catalog.enrich import EnrichmentResult

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
    assert seen == {"app": "upnext.web.api:app", "host": "127.0.0.1", "port": 9999}
