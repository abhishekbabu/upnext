# upnext

A personal watch tracker — what you're watching, what you've finished, and what
to put on next. Built to replace [TV Time](https://www.tvtime.com), which shut
down, and to own the data rather than rent it.

Shows first. Films use the same tables from day one, so adding them is data and
a second importer, not a migration.

## Where it is

Working today:

- **Import** — a TV Time GDPR export becomes a library, offline, in one command.
- **Enrichment** — every imported show resolved against TMDB, with real episode
  lists, artwork, air dates and runtimes.
- **A read API** — titles by status, a title with its episodes, up-next, stats.
- **The up-next query** — the next unwatched episode of everything in progress.
- **The app** — a poster shelf of what to watch next, the library filtered by
  status, a title with every episode and what you have seen, and the totals.

Not there yet: marking things watched from the app, films, and the diary. See
[Roadmap](#roadmap).

## Getting started

```sh
just install                       # venv, locked dependencies, git hooks
cp .env.template .env              # then add a TMDB key, see below
just import ~/Documents/tv-time-data
just enrich
just stats
just doctor                        # if any of the above surprises you
just ui                            # http://localhost:8000 — the app
```

### The TMDB key

Sign up at [themoviedb.org](https://www.themoviedb.org/signup), then request a
key under [Settings → API](https://www.themoviedb.org/settings/api). Choose
**Developer**: it is free, needs no card, and personal use is within its terms.
Copy the value labelled **API Key** — the v3 one, a 32-character hex string, not
the much longer read access token.

It goes in `.env` as `UPNEXT_TMDB_API_KEY`, which is gitignored and never
leaves the machine. `upnext import` and the API do not need it; `upnext enrich`
is the one command that does, and it says so up front rather than failing
partway through.

The library is a single SQLite file at `~/.upnext/library.db`. Delete it and
re-import; nothing else holds state. `just doctor` reports whether the key is
set, whether the library exists, and how much of it is still unenriched.

## Import, then enrich

The two steps are separate on purpose.

**Import** is a pure translation of the export. No network, no API key, and it
converges on re-runs — the same export imported twice leaves the library
exactly as it was. It reads five of the export's fifty-odd CSVs:

| File | What it gives |
| --- | --- |
| `tracking-prod-records-v2.csv` | every episode watch, and every rewatch |
| `followed_tv_show.csv` | which shows are followed, and whether archived |
| `user_show_special_status.csv` | the "for later" list and favourites |
| `user_tv_show_data.csv` | a per-show seen count |
| `tv_show_rate.csv` | star ratings |

Everything else in the export is account plumbing — access tokens, IP logs,
device identifiers, notification history — and is deliberately never read. **The
export is not safe to commit**: it contains live OAuth tokens. `.gitignore`
covers the usual folder names and `detect-private-key` runs pre-commit, but the
export belongs outside the repo.

**Enrich** is where TMDB comes in. It writes the episode list and matches the
imported history onto it. TV Time's show ids are TheTVDB ids, and
TMDB's `/find` endpoint maps one straight to a TMDB id — so enrichment is an
identity lookup, not a name search, for nearly everything. Name search is the
fallback, and it is strict: the first result only, and only when the year
agrees. A show TMDB has never heard of stays in the library exactly as the
export described it.

TMDB rather than IMDb because IMDb has no free public API; rather than TheTVDB
because v4 gates most data behind a subscriber PIN. TMDB also covers films,
which is what lets this grow past shows without a second provider.

### What the statuses mean

TV Time modelled a show with two booleans rather than one state. They translate:

| TV Time | upnext |
| --- | --- |
| followed, not archived | `watching` |
| followed and archived | `completed` — archiving is how TV Time says "seen it all" |
| unfollowed, with history | `stopped` |
| "for later" | `watchlist` |

A show with a seen count but no per-episode rows counts as history, not a
wishlist: TV Time keeps the tally after it drops the detail, and those shows
were watched.

### TMDB is the source of truth; the export is the source of history

The two answer different questions. TMDB says what a show *is* — its seasons,
its episodes, their names and air dates. The export says what was *watched*,
and it says it in whatever vocabulary the exporting service used.

So `episodes` holds TMDB's list and nothing else. An import never writes to it:
it records a viewing with the season and episode number the service gave, and
enrichment matches those to real episodes afterwards. Where they line up — the
overwhelming majority — a watch points at a catalog episode and progress is
simply a fraction. Where they do not, the viewing keeps the numbering it came
with and is shown apart, under **Not in TMDB** on the title page.

Matching is exact on episode number and never approximate: deciding a viewing
of S06E25 was "probably" S06E24 would put a guess into the one table that is
supposed to be the truth. Two disagreements about *shape* are resolvable on
evidence, though, and both are:

- **Seasons labelled by year.** TheTVDB numbers some shows' seasons by calendar
  year where TMDB numbers them 1..N. A season plainly labelled `2019` is
  resolved to whichever catalog season aired in 2019, from TMDB's own air
  dates. Sidemen Sundays matched nothing at all before this and now reads
  320 of 461.
- **A run the catalog keeps flat.** TMDB lists Yu-Gi-Oh! Duel Monsters as one
  season of 224 where TheTVDB splits the same 224 into five. The two orderings
  are laid side by side, but only when the catalog has exactly one season, the
  source names exactly as many episodes, and every watch that already matched
  by number agrees with the ordering — so the mapping is a hypothesis the
  existing matches confirm rather than an assumption. A partly watched show
  fails the second test and is left alone, because there is no way to know how
  long its seasons were.

`upnext relink` re-runs matching over a library that already has its episode
lists. It needs no network and no key; enrichment does it per title as it goes,
but only for titles it enriches.

Sometimes the disagreement is not about episodes but about what counts as one
show. TV Time files The Haunting of Bly Manor as season 2 of The Haunting, and
Whose Line's 2013 revival as seasons 9 to 12 of the 1998 one; TMDB keeps each
as its own title. `upnext move` puts those viewings where they belong:

```sh
upnext move --title 73 --season 2 --to 109958 --as-season 1
```

It is a person's call rather than an automatic one, and deliberately so: TMDB
has no "this is season 2 of that" relation, so anything automatic would be a
name search and a hope.

What is left over after that is a real disagreement, and worth seeing:

| Show | Reads as | Because |
| --- | --- | --- |
| Friends | 228 / 228, plus 8 | TheTVDB splits the eight double-length finales TMDB counts once |
| Yu-Gi-Oh! 5D's | 26 / 154, plus 52 | a partly watched run the catalog keeps flat, so its season lengths cannot be known |
| Jimmy Kimmel Live! | 0 / 3334, plus 5 | a nightly show the two number by different schemes entirely |
| Power Rangers | 210 / 973, plus 1 | one episode past where TMDB ends the season |

### Three other things the export gets wrong

- **Unnumbered episodes.** TV Time exports some shows with `episode_number` 0 —
  the whole of Beyblade, in the export this was built against. Those watches are
  kept against the show with no episode attached. The viewing count stays
  honest; the episode list is short.
- **Bulk marks.** Marking a season watched stamps every episode with the same
  second, and TV Time can issue two episodes with identical season/episode
  numbers. A watch is therefore identified by the source's own episode id where
  there is one, and by its numbering plus the timestamp where there is not.
- **Specials.** Season 0 is specials at every source, and TMDB leaves them out
  of `number_of_episodes`. They are stored, listed and counted as watched, but
  they are not progress — otherwise a watched special reads as 33 of 32.

## The app

One React app, built by Vite and served by the same FastAPI process — so there
is one port and one command in normal use:

```sh
just ui        # builds web/dist, then serves it and the API on :8000
```

While working on the front end, run the two halves apart and get hot reload:

```sh
just serve     # the API on :8000
just web       # Vite on :5173, proxying /api across to it
```

`web/dist` is gitignored and built on demand. Without it the API still serves —
`upnext serve` on a fresh clone is the API alone, and says so in the log.

```
web/src/
  lib/api.ts        the client, typed against the wire models in api.py
  lib/format.ts     posters, episode codes, progress, dates — pure and tested
  lib/queries.ts    every query and its cache key
  components/ui/    poster, progress bar, status badge, loading/empty/error
  panels/           UpNext, Library, Title, Stats — one per route
```

Color comes from semantic tokens (`bg-card`, `text-muted-foreground`) that
resolve through `light-dark()`, so light and dark are one class on `<html>` and
no JavaScript recolors anything. A lint rule rejects a raw Tailwind palette
utility, which cannot follow a mode change. `pnpm build` enforces a gzip budget
on the entry bundle, because everything in it is time the page is blank.

## The API

| Route | What it returns |
| --- | --- |
| `GET /api/titles?status=&kind=` | the library, with counted progress per title |
| `GET /api/titles/{id}` | one title, its episodes with watch counts, and any viewings TMDB cannot account for |
| `GET /api/up-next` | the next unwatched episode of everything in progress |
| `GET /api/stats` | episodes, titles, date range, runtime, counts by status |

"Next" is the lowest-numbered unwatched episode, not the highest watched plus
one — the second definition silently swallows a gap when someone skips around.
Season 0 is specials at every source, so it is never the next thing to watch.

## Development

```sh
just check              # lint, types, agent docs, tests, coverage floor — what CI runs
just fmt                # ruff fix + format
just doctor             # what this machine is set up for, and what it is not
just test               # the hermetic suite: no network, no key needed
just test-integration   # the tests that call TMDB (need a key)
just check-web          # the front end: lint, types, tests, build
```

Layout — ports and adapters, with the dependency arrows pointing inward:

```
src/upnext/
  domain/              the vocabulary, the errors, and the ports the core needs
    models.py            Title, Episode, Watch, Status — what everything speaks
    errors.py            every failure upnext raises on purpose
    ports.py             Catalog, WatchLibrary, ImportSource
  application/         the use cases, working against ports only
    enrichment.py        resolve a title against a catalog, fill in the data
    importing.py         read an export, write a library
  adapters/
    inbound/             the only layer that prints or returns a status code
      cli/                 commands.py, output.py
      web/api.py           the read API
    outbound/
      catalog/tmdb.py      the Catalog port, over TMDB
      importers/tvtime.py  the ImportSource port, over a TV Time export
      store/               schema.sql, connections, the repository
  config/settings.py   environment and .env
  bootstrap.py         the one module that names concrete implementations
```

`domain/` imports nothing else in the package, `application/` imports `domain/`
only, and `bootstrap.py` is the single place a concrete class is named. That is
what makes the roadmap cheap: a second importer is a registry entry, and a
second catalog is one class satisfying one protocol, neither of which is a
change to a use case.

## Roadmap

- A Letterboxd-ish diary of what was watched when.
- Writes: mark watched, rate, move between statuses.
- Films: a second importer and the same tables.
- Where to watch, from TMDB's providers endpoint.
- Season-level progress and a "what's airing this week" view.

Agent rules live in [`AGENTS.md`](AGENTS.md); `CLAUDE.md` is a symlink to it, so
there is one file rather than two that drift. `just check-agents` enforces that.
