from __future__ import annotations

from pathlib import Path

import pytest
from conftest import FakeCatalog, one_show

from upnext import bootstrap
from upnext.adapters.inbound.cli import commands as cli
from upnext.adapters.outbound.store.db import connect
from upnext.adapters.outbound.store.library import open_library
from upnext.domain.errors import CatalogError, ConfigurationError
from upnext.domain.models import Episode, Status, Title, TitleState, Watch
from upnext.domain.ports import CatalogMatch


def test_import_ingests_an_export_and_reports_what_it_did(export_dir: Path, tmp_path: Path, capsys) -> None:
    db = tmp_path / "library.db"
    assert cli.main(["--db", str(db), "import", str(export_dir)]) == 0

    out = capsys.readouterr().out
    assert "Imported 5 titles and 4 watches" in out
    assert "watching   1" in out
    with open_library(db) as library:
        assert library.stats().watches == 4


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
    with open_library(db) as library:
        for title in library.needing_enrichment():
            library.apply_enrichment(title.id, Title(name=title.name), enriched_at="2026-01-01T00:00:00+00:00")
    capsys.readouterr()

    assert cli.main(["--db", str(db), "enrich"]) == 0
    assert "every title already has catalog data" in capsys.readouterr().out


def test_an_unknown_import_source_is_refused(export_dir: Path, tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        cli.main(["--db", str(tmp_path / "l.db"), "import", str(export_dir), "--source", "letterboxd"])


class ThreeKindsOfAnswer(FakeCatalog):
    """Arrow is found, Beyblade's lookup fails, and nothing else is known."""

    def find_by_tvdb(self, tvdb_id: int) -> CatalogMatch | None:
        if tvdb_id == 70799:
            raise CatalogError("TMDB 400 for /find/70799")
        return CatalogMatch(catalog_id=1412) if tvdb_id == 257655 else None


def test_enrich_reports_found_not_found_and_failed_apart(export_dir: Path, tmp_path: Path, monkeypatch, capsys) -> None:
    """A title TMDB failed to serve is not one it has never heard of: the first
    is retried next run, and calling it "not found" sends someone to fix a
    match that was never attempted."""
    db = tmp_path / "library.db"
    cli.main(["--db", str(db), "import", str(export_dir)])
    capsys.readouterr()
    monkeypatch.setattr(bootstrap, "build_catalog", lambda settings: ThreeKindsOfAnswer())

    # Pending titles go by name, so the first three are Arrow, Beyblade, Friends.
    assert cli.main(["--db", str(db), "enrich", "--limit", "3"]) == 0

    out = capsys.readouterr().out
    assert "Matched 1 of 3." in out
    assert "Not found on TMDB (left as imported):\n  - Friends" in out
    assert "  - Beyblade: TMDB 400 for /find/70799" in out
    assert "The Flash" not in out


def test_a_key_tmdb_rejects_ends_the_run_with_what_to_fix(
    export_dir: Path, tmp_path: Path, monkeypatch, capsys
) -> None:
    class Rejected(FakeCatalog):
        def find_by_tvdb(self, tvdb_id: int) -> CatalogMatch | None:
            raise ConfigurationError("TMDB rejected the API key.")

    db = tmp_path / "library.db"
    cli.main(["--db", str(db), "import", str(export_dir)])
    monkeypatch.setattr(bootstrap, "build_catalog", lambda settings: Rejected())

    assert cli.main(["--db", str(db), "enrich"]) == 2
    assert "TMDB rejected the API key." in capsys.readouterr().err


def test_a_missing_subcommand_is_rejected() -> None:
    with pytest.raises(SystemExit):
        cli.main([])


def test_serve_hands_the_api_to_uvicorn(monkeypatch) -> None:
    from upnext.adapters.inbound.web.api import app

    seen = {}
    monkeypatch.setattr("uvicorn.run", lambda app, host, port: seen.update(app=app, host=host, port=port))
    assert cli.main(["serve", "--port", "9999"]) == 0
    assert seen == {"app": app, "host": "127.0.0.1", "port": 9999}


def test_serve_reads_the_library_named_by_db(tmp_path: Path, monkeypatch) -> None:
    """`--db` once reached every command but `serve`, which quietly served
    ~/.upnext instead."""
    from fastapi.testclient import TestClient

    from upnext.adapters.inbound.web.api import app

    db = tmp_path / "elsewhere.db"
    with open_library(db) as library:
        library.upsert_title(Title(name="Friends", tvdb_id=79168))
    monkeypatch.setattr("uvicorn.run", lambda app, host, port: None)
    try:
        cli.main(["--db", str(db), "serve"])
        names = [t["name"] for t in TestClient(app).get("/api/titles").json()]
    finally:
        app.dependency_overrides.clear()
    assert names == ["Friends"]


def test_relink_matches_watches_against_episodes_already_stored(export_dir: Path, tmp_path: Path, capsys) -> None:
    """Enrichment links as it goes, but only titles it enriches.

    A library already sitting on a full episode list would otherwise never pick
    up an improvement to how matching works.
    """
    db = tmp_path / "library.db"
    cli.main(["--db", str(db), "import", str(export_dir)])
    with open_library(db) as library:
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
    with open_library(db) as library:
        assert next(r for r in library.titles() if r.name == "Friends").episodes_watched == 2


def test_relink_names_the_titles_tmdb_cannot_account_for(export_dir: Path, tmp_path: Path, capsys) -> None:
    db = tmp_path / "library.db"
    cli.main(["--db", str(db), "import", str(export_dir)])
    with open_library(db) as library:
        arrow = next(row for row in library.titles() if row.name == "Arrow")
        library.apply_enrichment(
            arrow.id, Title(name="Arrow", total_episodes=1), enriched_at="2026-01-01T00:00:00+00:00"
        )
        library.upsert_episode(arrow.id, Episode(season_number=1, episode_number=1))
    capsys.readouterr()

    cli.main(["--db", str(db), "relink"])
    out = capsys.readouterr().out
    # Arrow's watch is of 3x13, which the one-episode list has no place for.
    assert "Arrow" in out
    # Friends was never enriched: its viewings are unasked, not disagreed with.
    assert "Friends" not in out


def test_relink_on_a_library_with_nothing_left_over_says_so(tmp_path: Path, capsys) -> None:
    db = tmp_path / "library.db"
    connect(db).close()
    assert cli.main(["--db", str(db), "relink"]) == 0
    assert "Every watch is accounted for" in capsys.readouterr().out


def a_haunting_library(db: Path) -> int:
    """A library filing one show's sequel as its second season, as TV Time does."""
    with open_library(db) as library:
        title_id = library.upsert_title(Title(name="The Haunting", tvdb_id=345246))
        library.set_state(title_id, TitleState(status=Status.COMPLETED))
        library.record_watch(title_id, Watch(watched_at="2018-10-12 00:00:00", episode=(1, 1)))
        library.record_watch(title_id, Watch(watched_at="2020-10-09 00:00:00", episode=(2, 1)))
    return title_id


def test_move_sends_a_season_to_the_title_it_belongs_to(tmp_path: Path, monkeypatch, capsys) -> None:
    db = tmp_path / "library.db"
    title_id = a_haunting_library(db)

    monkeypatch.setattr(
        bootstrap,
        "build_catalog",
        lambda settings: one_show("The Haunting of Bly Manor", 109958, [(1, 1)]),
    )
    assert (
        cli.main(
            ["--db", str(db), "move", "--title", str(title_id), "--season", "2", "--to", "109958", "--as-season", "1"]
        )
        == 0
    )

    out = capsys.readouterr().out
    assert "Moved 1 watches from The Haunting season 2 to The Haunting of Bly Manor." in out
    assert "1 matched an episode there." in out


def test_move_reports_what_the_target_could_not_place(tmp_path: Path, monkeypatch, capsys) -> None:
    db = tmp_path / "library.db"
    title_id = a_haunting_library(db)

    # A target whose episode list has no place for the moved viewing.
    monkeypatch.setattr(bootstrap, "build_catalog", lambda settings: one_show("Bly Manor", 109958, [(1, 9)]))
    cli.main(["--db", str(db), "move", "--title", str(title_id), "--season", "2", "--to", "109958", "--as-season", "1"])

    assert "1 did not — see the title page." in capsys.readouterr().out


def test_move_from_a_title_that_does_not_exist_says_so(tmp_path: Path, capsys) -> None:
    db = tmp_path / "library.db"
    connect(db).close()
    assert cli.main(["--db", str(db), "move", "--title", "999", "--season", "2", "--to", "1"]) == 2
    assert "No title with id 999" in capsys.readouterr().err


def test_move_without_a_key_explains_itself(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("UPNEXT_TMDB_API_KEY", "")
    db = tmp_path / "library.db"
    title_id = a_haunting_library(db)
    assert cli.main(["--db", str(db), "move", "--title", str(title_id), "--season", "2", "--to", "1"]) == 2
    assert "No TMDB API key" in capsys.readouterr().err


def test_enrich_refuses_a_limit_of_nothing(tmp_path: Path) -> None:
    """`--limit 0` once meant no limit at all."""
    with pytest.raises(SystemExit):
        cli.main(["--db", str(tmp_path / "l.db"), "enrich", "--limit", "0"])
