from __future__ import annotations

from pathlib import Path

from upnext.config.settings import PROJECT_ROOT, load_settings


def test_the_env_file_is_found_by_absolute_path() -> None:
    """`upnext` is a console script; it must not depend on the working directory."""
    assert Path(load_settings().model_config["env_file"]).is_absolute()
    assert (PROJECT_ROOT / "pyproject.toml").exists()


def test_the_environment_overrides_the_defaults(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("UPNEXT_TMDB_API_KEY", "abc123")
    monkeypatch.setenv("UPNEXT_DB_PATH", str(tmp_path / "elsewhere.db"))
    settings = load_settings()
    assert settings.tmdb_api_key == "abc123"
    assert settings.db_path == tmp_path / "elsewhere.db"


def test_the_key_is_empty_by_default(monkeypatch) -> None:
    monkeypatch.setenv("UPNEXT_TMDB_API_KEY", "")
    assert load_settings().tmdb_api_key == ""
