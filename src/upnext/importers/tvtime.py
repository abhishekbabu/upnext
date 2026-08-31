"""Reconstruct a library from a TV Time GDPR export.

The export is a folder of CSVs dumped straight from TV Time's tables, with no
schema and considerable redundancy. Four files carry everything upnext needs:

  tracking-prod-records-v2.csv  every episode watch, with a `key` prefixed
                                "watch-episode" or "rewatch-episode". This is
                                the authoritative history; seen_episode_source
                                .csv is a strict subset of it.
  followed_tv_show.csv          which shows are followed, and whether archived.
  user_show_special_status.csv  the "for later" watchlist and favourites.
  user_tv_show_data.csv         a per-show seen count, which exists for shows
                                whose per-episode rows the export omits.
  tv_show_rate.csv              1-5 star ratings.

Everything else in the export is account plumbing — tokens, IP logs, device
identifiers, notification history — and is deliberately not read.

Show ids throughout are TheTVDB ids, which is why enrichment resolves through
TMDB's /find endpoint rather than searching by name.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from upnext.models import ImportedTitle, Kind, Status, Title, TitleState, Watch

SOURCE = "tvtime"

WATCH_RECORDS = "tracking-prod-records-v2.csv"
FOLLOWED = "followed_tv_show.csv"
SPECIAL_STATUS = "user_show_special_status.csv"
SHOW_DATA = "user_tv_show_data.csv"
RATINGS = "tv_show_rate.csv"

# The files an export must contain for the import to mean anything. The rest
# are optional: an account with no ratings simply has no tv_show_rate.csv.
REQUIRED = (WATCH_RECORDS, SHOW_DATA)


class ExportError(Exception):
    """The folder given is not a usable TV Time export."""


def _rows(export_dir: Path, filename: str) -> list[dict[str, str]]:
    path = export_dir / filename
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _int(value: str | None) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except ValueError:
        return None


def _status_for(*, followed: dict[str, str] | None, for_later: bool, has_history: bool) -> Status:
    """Translate TV Time's two booleans into one status.

    TV Time modelled a show with `active` (still followed) and `archived`
    (done with it) rather than a single state, so:

      active, not archived  -> watching
      active and archived   -> completed; archiving is how TV Time says "seen it all"
      not active            -> stopped, if there is any history to have stopped
      no follow row at all  -> the watchlist, or stopped if it was ever watched
    """
    if followed is not None:
        active = followed.get("active") == "1"
        archived = followed.get("archived") == "1"
        if not active:
            return Status.STOPPED
        return Status.COMPLETED if archived else Status.WATCHING
    if for_later:
        return Status.WATCHLIST
    return Status.STOPPED if has_history else Status.WATCHLIST


def read_export(export_dir: Path | str) -> list[ImportedTitle]:
    """Parse an export folder into titles the library can ingest.

    Nothing here touches the network: an import is a pure translation of the
    export, and TMDB only enters at enrichment.
    """
    export_dir = Path(export_dir)
    if not export_dir.is_dir():
        raise ExportError(f"{export_dir} is not a directory")
    missing = [name for name in REQUIRED if not (export_dir / name).exists()]
    if missing:
        raise ExportError(f"{export_dir} is missing {', '.join(missing)} — is this a TV Time export?")

    watches_by_show: dict[str, list[Watch]] = defaultdict(list)
    names_from_watches: dict[str, str] = {}
    for row in _rows(export_dir, WATCH_RECORDS):
        key = row.get("key") or ""
        if not key.startswith(("watch-episode", "rewatch-episode")):
            continue
        show_id = row.get("s_id")
        season, number = _int(row.get("season_number")), _int(row.get("episode_number"))
        if not show_id:
            continue
        if row.get("series_name"):
            names_from_watches[show_id] = row["series_name"]
        watches_by_show[show_id].append(
            Watch(
                watched_at=row["created_at"],
                episode=_episode_ref(season, number),
                is_rewatch=key.startswith("rewatch-episode"),
                source=SOURCE,
                source_episode_id=row.get("ep_id") or None,
            )
        )

    followed = {row["tv_show_id"]: row for row in _rows(export_dir, FOLLOWED)}
    show_data = {row["tv_show_id"]: row for row in _rows(export_dir, SHOW_DATA)}
    ratings = {row["tv_show_id"]: _int(row.get("rating")) for row in _rows(export_dir, RATINGS)}

    special = _rows(export_dir, SPECIAL_STATUS)
    for_later = {row["tv_show_id"] for row in special if row.get("status") == "for_later"}
    favorites = {row["tv_show_id"] for row in special if row.get("status") == "favorite"}

    # Every file that mentions a show also names it, and a watchlist entry is
    # often mentioned nowhere else, so names are collected from all of them.
    names = {**names_from_watches, **_collect_names(export_dir, followed, show_data, special)}

    # A show can appear in any of these files independently, so the set of
    # shows to import is their union rather than any one file's rows.
    show_ids = set(watches_by_show) | set(followed) | set(show_data) | for_later | favorites | set(ratings)

    imported: list[ImportedTitle] = []
    for show_id in sorted(show_ids, key=int):
        name = names.get(show_id)
        if name is None:
            continue
        watches = sorted(watches_by_show.get(show_id, []), key=lambda w: w.watched_at)
        base_name, year = _split_year(name)
        follow_row = followed.get(show_id)

        rating = ratings.get(show_id)
        reported = _int((show_data.get(show_id) or {}).get("nb_episodes_seen"))
        imported.append(
            ImportedTitle(
                title=Title(name=base_name, kind=Kind.SHOW, year=year, tvdb_id=int(show_id)),
                state=TitleState(
                    status=_status_for(
                        followed=follow_row,
                        for_later=show_id in for_later,
                        # A seen count with no per-episode rows still counts as
                        # history: TV Time keeps the tally after it drops the
                        # detail, and those shows were watched, not wishlisted.
                        has_history=bool(watches) or bool(reported),
                    ),
                    is_favorite=show_id in favorites,
                    # TV Time rated out of 5; upnext keeps a 10-point scale so
                    # half-star precision is available later without a migration.
                    rating=rating * 2 if rating else None,
                    reported_watched=reported,
                    followed_at=(follow_row or {}).get("created_at") or None,
                ),
                watches=watches,
            )
        )
    return imported


def _episode_ref(season: int | None, number: int | None) -> tuple[int, int] | None:
    """Which episode a watch is of, or None when the export does not say.

    Episodes are 1-indexed everywhere, so an episode_number of 0 is TV Time's
    "I recorded the watch but not which episode" — the whole of Beyblade comes
    through that way. Those watches are kept against the show with no episode
    attached rather than folded into a single fictional slot, which is what
    keeps the count honest.
    """
    if season is None or number is None or number < 1:
        return None
    return (season, number)


def _collect_names(
    export_dir: Path,
    followed: dict[str, dict],
    show_data: dict[str, dict],
    special: list[dict[str, str]],
) -> dict[str, str]:
    names: dict[str, str] = {}
    sources: list[list[dict[str, str]]] = [
        _rows(export_dir, RATINGS),
        special,
        list(show_data.values()),
        list(followed.values()),
    ]
    for rows in sources:
        for row in rows:
            name = row.get("tv_show_name")
            if name and row.get("tv_show_id"):
                names[row["tv_show_id"]] = name
    return names


def _split_year(name: str) -> tuple[str, int | None]:
    """Pull the disambiguating year out of names like "The Flash (2014)".

    TV Time bakes it into the title; TMDB keeps it separate, and matching one
    against the other goes better when upnext does too. A parenthetical that
    is not a four-digit year — "Whose Line Is It Anyway? (US)" — is left alone.
    """
    if name.endswith(")") and "(" in name:
        head, _, tail = name.rpartition("(")
        candidate = tail[:-1]
        if candidate.isdigit() and len(candidate) == 4:
            return head.strip(), int(candidate)
    return name, None
