"""Report what this machine is set up for, and what it is not.

Answers the question that costs the most time to answer any other way: is the
key missing, is the library empty, or is something actually broken? Opening the
library applies its schema, which is the only write; it never prints a secret.

    just doctor
"""

from __future__ import annotations

from upnext.adapters.outbound.store.library import open_library
from upnext.config.settings import PROJECT_ROOT, Settings

OK = "✓"
MISSING = "·"

KNOWN_KEYS = {f"{Settings.model_config['env_prefix']}{name}".upper() for name in Settings.model_fields}


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
    path = settings.db_path
    if not path.exists():
        return [f"{MISSING} no library at {path} — run `upnext import <export-dir>`"]

    with open_library(path) as library:
        total = library.count_titles()
        pending = len(library.needing_enrichment())
        watches = library.stats().watches

    if total == 0:
        return [f"{MISSING} library at {path} is empty — run `upnext import <export-dir>`"]

    lines = [f"{OK} library at {path}: {total} titles, {watches} watches"]
    if pending:
        lines.append(f"  {MISSING} {pending} titles not yet enriched — run `upnext enrich`")
    else:
        lines.append(f"  {OK} every title enriched")
    return lines


def main() -> int:
    settings = Settings()
    print("upnext doctor\n")
    for line in check_env_file():
        print(line)
    print(check_key(settings))
    for line in check_library(settings):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
