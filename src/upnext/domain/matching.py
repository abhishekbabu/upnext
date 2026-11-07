"""Which catalog episode each recorded viewing is of.

The export numbers what was watched; the catalog numbers what exists. This is
where the two meet, and it decides on evidence or not at all.

Episode numbers match exactly and never approximately. Deciding that a viewing
of S06E25 was "probably" S06E24 would put a guess into the one table that is
supposed to be the catalog's, and Friends' eight split finales are exactly that
case.

Two disagreements about *shape* are resolvable, because each can be shown
rather than assumed:

- A season the source labelled with a year. TheTVDB labels some shows' seasons
  by calendar year where TMDB numbers them 1..N — Sidemen Sundays is 2019 at
  one and season 4 at the other, with identical numbering inside. The catalog's
  own air dates say which season that was.
- A run the source split and the catalog keeps flat. TMDB lists Yu-Gi-Oh! Duel
  Monsters as one season of 224; TheTVDB splits the same 224 into five. The two
  orderings can be laid side by side, but only when they are the same length
  and every viewing already matched by number agrees with the ordering. That
  last check is what makes it a hypothesis the matches confirm rather than an
  assumption.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

SEASON_IS_A_YEAR = 1900
"""A season number at or above this is a calendar year, not an index. Television
has not run to a nineteen-hundredth season of anything."""

type Numbering = tuple[int, int]
"""(season, episode), as the source wrote it."""


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    """One episode of the catalog's list, as matching needs to see it."""

    id: int
    season_number: int
    episode_number: int
    air_date: str | None = None


def match(
    catalog: list[CatalogEntry], *, unlinked: set[Numbering], linked: dict[Numbering, int]
) -> dict[Numbering, int]:
    """The catalog episode for each numbering that still has unmatched viewings.

    `linked` is what earlier runs settled. It is never revisited, and it is the
    evidence the flattened reading has to agree with. A numbering absent from
    the result is a viewing of something the catalog's list does not contain.
    """
    by_number = {(e.season_number, e.episode_number): e.id for e in catalog}

    found = {key: by_number[key] for key in unlinked if key in by_number}
    for season, number in unlinked - found.keys():
        aired = _season_aired_in(catalog, season) if season >= SEASON_IS_A_YEAR else None
        if aired is not None and (aired, number) in by_number:
            found[(season, number)] = by_number[(aired, number)]

    watched = unlinked | linked.keys()
    found |= _flattened(catalog, pending=unlinked - found.keys(), settled=linked | found, watched=watched)
    return found


def _season_aired_in(catalog: list[CatalogEntry], year: int) -> int | None:
    """The numbered season most of whose episodes aired in `year`.

    By weight of episodes, so a season straddling New Year resolves to the year
    most of it belongs to; ties go to the earlier season.
    """
    counts = Counter(
        e.season_number for e in catalog if e.season_number > 0 and e.air_date and e.air_date[:4] == str(year)
    )
    if not counts:
        return None
    return min(counts, key=lambda season: (-counts[season], season))


def _flattened(
    catalog: list[CatalogEntry],
    *,
    pending: set[Numbering],
    settled: dict[Numbering, int],
    watched: set[Numbering],
) -> dict[Numbering, int]:
    """The ordinal reading of a split run against a flat one, if it holds.

    Three conditions, all of which must:

    1. The catalog has exactly one numbered season. Anything else and the two
       disagree about content, not grouping.
    2. The source names exactly as many distinct episodes as that season holds.
       A partly watched show cannot satisfy this, which is the point: without a
       complete run the source's season lengths are unknown and the offsets
       would be invented.
    3. At least one viewing already matched, and every one that did lands where
       the ordering says.
    """
    numbered = sorted((e for e in catalog if e.season_number > 0), key=lambda e: (e.season_number, e.episode_number))
    if len({e.season_number for e in numbered}) != 1:
        return {}
    source = sorted(key for key in watched if key[0] > 0)
    if len(source) != len(numbered):
        return {}

    ordinal = dict(zip(source, (e.id for e in numbered), strict=True))
    confirmed = {key: episode_id for key, episode_id in settled.items() if key[0] > 0}
    if not confirmed or any(ordinal[key] != episode_id for key, episode_id in confirmed.items()):
        return {}
    return {key: ordinal[key] for key in pending if key in ordinal}
