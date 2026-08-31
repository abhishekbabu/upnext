# upnext — Agent Rules

Project overview, setup, architecture and commands live in [`README.md`](README.md).
This file is only the rules an agent needs that the README does not already state.

## Before committing

`just check` (lint, format, types, tests, 95% coverage floor) must pass. The
pre-commit hooks run the same gates, so a commit that skips them will fail anyway.

Update `README.md` in the same commit when behavior, commands, dependencies or
environment variables change. Prose documentation lives there and in this file;
do not add new doc files.

## The layering

Dependency arrows point inward. `domain/` imports nothing else in the package;
`application/` imports `domain/` only; `adapters/` may import both. Nothing
inward of `adapters/` may import outward of it — if a use case needs something
an adapter has, name it as a port.

```
domain/       models.py, errors.py, ports.py   — the vocabulary and the interfaces
application/  enrichment.py, importing.py      — use cases, ports-only collaborators
adapters/inbound/    cli/, web/                — the only place that prints or exits
adapters/outbound/   catalog/, importers/, store/
config/       settings.py
bootstrap.py  the one module that names concrete implementations
```

**Ports.** A port speaks `domain.models`, never a vendor's JSON. `Catalog`
returning TMDB dicts would put the application back in the business of knowing
what TMDB is, which is the coupling the port exists to remove. Translation
happens inside the adapter, on the way out.

**Composition.** Only `bootstrap.py` may name a concrete implementation. A use
case that constructs its own collaborator has hard-coded a vendor; take it as an
argument instead. Adding a catalog, an importer or a second store is an entry in
`bootstrap`, not a branch at a call site.

## Hard rules

**Errors.** Nothing signals failure by return value — no `None`, no `[]`, no
`"error: ..."` string, none of which a caller can tell from a real result. Raise
an `UpnextError` subclass from `domain/errors.py`; an empty list is a valid
*answer*, a failed request is not. Never `print` or `sys.exit` outside
`adapters/inbound/`. `raise ... from e` when re-raising.

`RetryableCatalogError` never escapes an adapter — the retry policy that catches
it lives there, and what reaches the application is a result or a `CatalogError`.
`ConfigurationError` is separate from both because it is answerable: the message
says what to put where, and retrying never substitutes for it.

**Dates and times.** Aware UTC for anything persisted or compared — never naive
`datetime.now()`. Timestamps from a source are stored as the source wrote them,
because a watch's identity depends on the exact string.

**The library converges.** Every write is idempotent on its natural key: the same
export imported twice, or enrichment run twice, must leave the library exactly as
it was. A change that makes a re-run duplicate rows is a bug even if it passes.

**What enrichment may overwrite.** `ENRICHABLE` in `store/library.py`, and
nothing else. `name` and `year` are deliberately excluded — an import names a
title from the user's own history, and a bad catalog match must not silently
rewrite the library.

**Matching is strict.** A TheTVDB id is an identity; a name search is a guess.
Search is the fallback only, first result only, and only when the year agrees.
A title the catalog has never heard of stays exactly as the export described it —
a wrong match corrupts the library far more visibly than a missing one.

**"Next" is the lowest unwatched episode**, never the highest watched plus one,
which silently swallows a gap when someone skips around. Season 0 is specials at
every source, so it is never the next thing to watch — but its episodes are still
stored, and filtered at query time.

**The export is not safe to commit.** A TV Time export contains live OAuth
tokens. `.gitignore` covers the usual folder names and `detect-private-key` runs
pre-commit, but the export belongs outside the repo. Only the five CSVs the
importer names are ever read; everything else in an export is account plumbing.

**Naming.** `<Vendor>Client` for API clients (`TMDBClient`), `<Service>Export`
for import sources (`TVTimeExport`), `<What>Error` for domain errors. Domain
names never carry a vendor: the port is `Catalog`, not `TMDB`. Test modules
mirror the module they cover.

**Types.** Avoid `Any`; prefer builtin generics and PEP 604 unions, which ruff's
`UP` rules enforce. Do not disable a lint globally to fix one call site.

**Tests.** The default suite is hermetic — no network, no key, no `~/.upnext`.
Anything hitting TMDB is marked `integration` and deselected by default. Fakes
implement the port, not the vendor's payload shape.

**Dependencies.** Anything imported directly gets declared directly, never relied
on transitively. Bound both ends (`>=X.Y.Z,<NEXT_MAJOR`), then `just lock`. On
the front end, `pnpm add` and commit `pnpm-lock.yaml` — CI installs `--frozen-lockfile`.

## The front end

`just check-web` must pass alongside `just check`; CI runs them as separate jobs.

**Color comes from tokens**, never a raw Tailwind palette utility — `bg-card`,
not `bg-neutral-50`. A raw utility cannot follow a mode change, and eslint
rejects one. Light and dark are one class on `<html>`; the tokens resolve
through `light-dark()` and no JavaScript recolors anything.

**The API client is the contract.** `web/src/lib/api.ts` mirrors the wire models
in `adapters/inbound/web/api.py`. Change one and change the other in the same
commit — a field read here that the server stopped sending is a typecheck
failure, which is the point.

**Formatting lives in `lib/format.ts`** and is pure and tested. A panel that
formats a date or an episode code itself will drift from the one beside it.
Anything locale-dependent takes the locale as an argument, so a test can pin it.

**The entry bundle has a gzip budget** enforced by `pnpm build`. Everything in
it is time the page is blank. Raise it deliberately, with the reason in the
commit, or defer the code behind a dynamic import.
