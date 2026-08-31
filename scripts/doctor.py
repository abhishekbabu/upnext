"""Report what this machine is set up for, and what it is not.

Answers the question that costs the most time to answer any other way: is the
key missing, is the library empty, or is something actually broken? Reads only
— it never writes to the library and never prints a secret.

    just doctor
"""

from __future__ import annotations

from pathlib import Path

from upnext.adapters.outbound.store.db import connect
from upnext.adapters.outbound.store.library import Library
from upnext.config.settings import PROJECT_ROOT, Settings, load_settings

OK = "✓"
MISSING = "·"

# Every environment variable settings.py understands, with the prefix stripped.
KNOWN_KEYS = {f"UPNEXT_{name.upper()}" for name in Settings.model_fields}


def check_env_file() -> list[str]:
    """Flag keys in .env that no setting reads — almost always a typo.

    Values are never read or printed here; only the names on the left of the
    `=` are looked at.
    """
    env = PROJECT_ROOT / ".env"
    if not env.exists():
        return [f"{MISSING} no .env — copy .env.template to .env"]

    lines = []
    for raw in env.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name = line.split("=", 1)[0].strip()
        if name.upper() not in KNOWN_KEYS:
            lines.append(f"  ! {name} in .env is not a setting upnext reads — typo?")
    return [f"{OK} .env found at {env}", *lines]


def check_key(settings: Settings) -> str:
    if not settings.tmdb_api_key:
        return f"{MISSING} no TMDB key — `upnext enrich` will not run (see .env.template)"
    # The length is the only thing worth saying out loud. A v3 key is 32 hex
    # characters; the much longer read access token is the usual mix-up.
    key = settings.tmdb_api_key
    if len(key) != 32:
        return f"  ! TMDB key is {len(key)} characters, not 32 — is this the v4 read token rather than the v3 key?"
    return f"{OK} TMDB key set ({len(key)} characters)"


def check_library(settings: Settings) -> list[str]:
    path = Path(settings.db_path).expanduser()
    if not path.exists():
        return [f"{MISSING} no library at {path} — run `upnext import <export-dir>`"]

    conn = connect(path)
    try:
        library = Library(conn)
        total = library.count_titles()
        pending = len(library.needing_enrichment())
        stats = library.stats()
    finally:
        conn.close()

    if total == 0:
        return [f"{MISSING} library at {path} is empty — run `upnext import <export-dir>`"]

    lines = [f"{OK} library at {path}: {total} titles, {stats['watches']} watches"]
    if pending:
        lines.append(f"  {MISSING} {pending} titles not yet enriched — run `upnext enrich`")
    else:
        lines.append(f"  {OK} every title enriched")
    return lines


def main() -> int:
    settings = load_settings()
    print("upnext doctor\n")
    for line in check_env_file():
        print(line)
    print(check_key(settings))
    for line in check_library(settings):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
