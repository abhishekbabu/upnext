"""Configuration, read from the environment and an optional .env."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The .env is found by absolute path rather than by name so that `upnext` picks
# it up wherever it is run from, not only from the project directory.
PROJECT_ROOT = Path(__file__).resolve().parents[3]

DEFAULT_DB_PATH = Path.home() / ".upnext" / "library.db"


class Settings(BaseSettings):
    """Everything upnext needs to run, with working defaults for all of it.

    Only the TMDB key has no default: import and browsing work without it, and
    the commands that ask TMDB — `enrich` and `move` — fail loudly when it is
    missing.
    """

    model_config = SettingsConfigDict(
        env_prefix="UPNEXT_",
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    db_path: Path = Field(default=DEFAULT_DB_PATH)
    tmdb_api_key: str = Field(default="")
    # TMDB serves artwork off a separate CDN; the client only ever stores the
    # path, so the base lives here and the size is chosen at render time.
    tmdb_image_base: str = Field(default="https://image.tmdb.org/t/p")
    tmdb_language: str = Field(default="en-US")
    # A courtesy pause between TMDB calls. Their published limit is generous,
    # but enrichment walks every season of every show in one go.
    tmdb_min_interval_seconds: float = Field(default=0.05)

    host: str = Field(default="127.0.0.1")
    port: int = Field(default=8000)

    @field_validator("db_path")
    @classmethod
    def _expand_home(cls, path: Path) -> Path:
        # A shell expands `~` on the command line, but not inside .env.
        return path.expanduser()
