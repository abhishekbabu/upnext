# Audit Playbook

What to look for, per category. Each subagent (or direct pass) gets the relevant
section plus the **Finding format** at the bottom.

A finding is only a finding with evidence. "Probably counts something wrong" is
not a finding; `library.py:271 counts specials into a total that excludes them`
is.

Before reporting anything, check it against `AGENTS.md`. A great many things
that look wrong here are decisions with reasons written down — season 0 kept out
of progress but counted in the library totals, `name` and `year` deliberately
excluded from `ENRICHABLE`, a watch the export could not number carrying no
episode at all. Those are settled. **A stale rule is itself a finding**: if the
code has drifted from what `AGENTS.md` says, report the drift — one of the two
is wrong and both matter.

---

## 1. Correctness

The highest-trust category — real bugs found by reading, not speculation.

- **Failure signalled by return value.** The house rule is absolute: raise an
  `UpnextError` subclass from `domain/errors.py`, never return `None`, `[]` or
  an `"error: ..."` string a caller cannot tell from a real answer. An empty
  list is a valid answer; a failed request is not. Look for `except ...: return
  None`, a bare `return []` on an error path, error text returned as data.
- **`RetryableCatalogError` escaping an adapter.** It exists inside the retry
  policy. If it can reach `application/`, the application is being handed a
  failure it has no way to interpret.
- **Swallowed exceptions.** `except Exception: pass`, a log with no re-raise on
  a path the caller needs to know about, `raise X` without `from e`. The one
  sanctioned swallow is a season TMDB will not serve, in `fetch_show`, and it is
  commented as such.
- **Naive datetimes.** `datetime.now()` or `date.today()` without a timezone for
  anything persisted or compared. Timestamps from a source are stored exactly as
  the source wrote them, because a watch's identity depends on the string.
- **The catalog/history split.** `episodes` is TMDB's list and nothing else; an
  import never writes to it. Anything creating an episode row from a watch is
  the bug this repo already fixed once, coming back.
- **Matching that guesses.** Episode numbers match exactly. The two sanctioned
  shape rules are evidence-led — a season at or above `SEASON_IS_A_YEAR`
  resolving by air date, and a flat catalog season mapped ordinally *only* when
  the lengths agree and every already-matched watch confirms the ordering. A new
  rule without confirming evidence is a correctness finding, not a feature.
- **The three counts.** `watches` (viewings), `episodes_watched` (distinct,
  specials excluded, matched to the catalog) and `unmatched_watched` are
  different numbers. Every counting bug this repo has had was two of them
  confused — 33 of 32, 236 of 228. Any comparison of a count to
  `total_episodes` must be counting what TMDB counted.
- **Convergence.** Every write is idempotent on its natural key. A change that
  makes re-importing an export or re-running enrichment duplicate rows is a bug
  even when the tests pass.
- **Migrations.** `migrate()` runs on every `connect()` and must be safe every
  time. Look for a step that is not idempotent, one that runs after
  `executescript` when it needed to run before, and any `DROP`/`DELETE` whose
  test does not prove what survived it.
- **Boundary conditions.** An empty library, a title with no episodes, a season
  0 with no season 1, a watch with no episode, an export naming a season the
  catalog ends before.
- **Type escape hatches.** `Any`, `# type: ignore`, `cast` — each is a place the
  checker was overruled. Cluster them; a cluster usually marks a real modelling
  gap.
- **Resource handling.** Unclosed connections or sessions, missing `finally`, a
  file left behind on the error path. One SQLite connection per request, closed
  on the way out — a cached one is not an option across threads.

## 2. Security

Frame findings as defensive maintenance: name the pattern, the impact, and the
remediation. No runnable misuse examples.

**Handling rule: never copy a secret value into a finding or a plan.** Name the
`file:line` and the credential type only ("TMDB key read at `settings.py:33`"),
and always recommend rotation — a committed secret is burned even after deletion.

- **Credential hygiene.** Anything that would put `.env` into a commit; the key
  read through `os.getenv` at a call site instead of `Settings`; a value logged,
  printed by `doctor`, or returned by an API route. `scripts/doctor.py` reports
  the key's *length* and never its characters, deliberately.
- **The export.** A TV Time export contains live OAuth tokens, IP logs and
  device identifiers. The importer reads five named CSVs and must never read the
  rest. Anything widening that, or copying an export into the repo, is a finding.
  `detect-private-key` runs pre-commit as the backstop.
- **Untrusted third-party data.** Every TMDB response is data from outside. Look
  for it reaching a filesystem path, an interpreter, or a format string without
  validation — and for a catalog field being treated as a command.
- **Input contracts.** FastAPI routes trusting a query or path parameter without
  a schema; a path parameter interpolated into a filesystem path. The SPA
  fallback returns files from `web/dist` by request path — that is the one place
  traversal would matter.
- **Error detail exposure.** Stack traces or upstream error bodies returned to
  the client. `CatalogError` messages carry TMDB's response text truncated;
  anything surfacing that to a browser is a finding.
- **Dependency posture.** `uv run pip-audit` read-only if available. Report only
  critical/high advisories affecting reachable code.

## 3. Performance

Algorithmic and architectural wins, not micro-optimizations.

- **Repeated work.** The same TMDB fetch performed twice, the same query run per
  row. `titles()` deliberately does its counting in one grouped query; an N+1
  reintroduced per title is the shape to watch for.
- **Enrichment cost.** It walks every season of every show. A change that turns
  one request per season into one per episode is a real regression against a
  rate-limited API — TMDB's per-episode external ids are the tempting instance.
- **Rate limiting.** `min_interval_seconds` and the `Retry-After` sleep exist
  because enrichment runs hundreds of calls in a burst. Removing either, or
  parallelising the walk, is a finding.
- **SQL shape.** A missing index on a column joined or filtered per request;
  a correlated subquery per row where a join would do; `SELECT *` feeding a
  read model that needs four columns.
- **Front end.** The entry bundle has a hard gzip budget checked by the build.
  Watch for a heavyweight dependency pulled in for trivial use, and anything
  that should be deferred past first paint.
- **CI.** Redundant steps, missing caching, a gate that duplicates another.

## 4. Tests

The goal is not a percentage — it is *which untested code is dangerous*. See the
`review-tests` skill for the quality bar; this category is about coverage shape.

- Map the paths that matter — the matching passes, the migrations, the counting
  queries, `up_next`, the import's identity rules — and check which have zero or
  trivial coverage.
- High churn with no tests is the top refactor risk; flag as "characterization
  tests first" and order it before any plan that touches that code.
- Coverage is gated at 95%, which means the number tells you nothing about
  quality. Look for tests written to move it: no assertion, `assert x is not
  None`, a loop asserting something the types already guarantee.
- Hermeticism: anything reaching TMDB or the real `~/.upnext/library.db` without
  the `integration` marker, or writing outside `tmp_path`.
- Over-marking: a test marked `integration` that did not need to be is a test
  `just check` never runs.

## 5. Tech debt & architecture

- **Layering violations.** The rule points inward only: `domain/` imports
  nothing else in the package, `application/` imports only `domain/`, adapters
  implement ports, `bootstrap.py` alone names a concrete implementation.
  `tests/test_architecture.py` enforces this by walking the imports — so a
  violation is usually a *new entry in its `ALLOWED` table*, which is the more
  interesting finding.
- **Vendor names inside the core.** The port is `Catalog`, not `TMDB`. Anything
  in `domain/` or `application/` that knows TMDB exists, handles its JSON, or
  names one of its fields belongs in the adapter.
- **A use case constructing its collaborator.** Ports are taken as arguments on
  purpose. A default that instantiates a `TMDBClient` hard-codes a vendor into
  the layer that exists to avoid it.
- **The second instance.** Extract on the second occurrence, not the third. Look
  for logic written twice that belongs in the store, the application layer, or
  `domain/` (rules that hold regardless of source).
- **Naming drift.** `<Vendor>Client` for API clients, `<Service>Export` for
  import sources, `<What>Error` for domain errors. Domain names carry no vendor.
  Test modules mirror the module they cover.
- **Front-end structure.** `panels/` holds one page each; anything used by a
  second caller belongs in `components/ui/`. A card, loading state or control
  reimplemented per panel is the drift this rule exists to stop. Color from a
  raw Tailwind palette utility instead of a semantic token cannot follow a mode
  change, and eslint rejects it.
- **God modules.** Files an order of magnitude larger than the median.
  `store/library.py` is the one to watch; it is already the largest module and
  every new query lands in it.
- **Dead code.** Settings nothing reads, `just` recipes for files nothing writes,
  wire fields no panel renders, commented-out blocks.

## 6. Dependencies

- Anything imported directly but not declared directly — the rule forbids relying
  on a transitive dependency.
- Unbounded or one-sided version constraints; the convention is
  `>=X.Y.Z,<NEXT_MAJOR` on both ends, then `just lock`.
- Major-version lag where staying behind has real cost (EOL, security cutoff).
- Two dependencies solving the same problem.
- `uv.lock` drift against `pyproject.toml`; `web/pnpm-lock.yaml` against
  `web/package.json`. CI installs `--locked` and `--frozen-lockfile`, so drift
  fails there rather than here.

## 7. DX & tooling

- A gate that exists locally but not in CI, or vice versa — CI runs the same
  `just` recipes, so adding one to the `justfile` should extend CI.
- `scripts/doctor.py` falling behind the settings it reports on, or reporting a
  value where it should report presence.
- Setup steps in `README.md` that are wrong or incomplete; an environment
  variable nothing declares, or a declared one nothing documents.
- Slow feedback: a gate that takes minutes, a test suite that could be narrowed.

## 8. Docs

Lowest default priority — flag only where absence has a concrete cost.

- `README.md` describing behavior the code no longer has. Stale is worse than
  missing, and the repo requires README updates in the same commit as a
  behavior, command, dependency or environment change.
- `AGENTS.md` over its 200-line cap, or a rule in it the code contradicts.
- A `CLAUDE.md` that is a real file rather than a symlink to its sibling — two
  real files drift and each tool reads a different one. `just check-agents`
  enforces both, so a failure here is a gate failure, not a note.

## 9. Direction — features and where to take this next

Forward-looking. **Grounding rule:** every suggestion must cite evidence from
this repo. A suggestion that could apply to any project ("add AI", "add dark
mode" — it has one already) is noise.

- **Unfinished intent:** TODO clusters around one theme, a settings field
  nothing reads, a wire field no panel renders, half-built modules.
- **Stated but undelivered:** anything `README.md` promises without code behind
  it. The roadmap names writes, films, a diary and watch providers.
- **The adjacent possible:** what the existing shape makes disproportionately
  cheap. `titles` is keyed by `kind` from the start, so films are a second
  importer and a second set of TMDB calls, not a migration. `ImportSource` is a
  registry entry. A second catalog is one class satisfying one protocol.
- **Surface asymmetries:** something the API can answer that no panel shows, or
  a read model carrying a field nothing renders.

Direction findings use the standard format with two adaptations: **Impact** is
user value (who wants this and why now), and **Confidence** reflects how grounded
the evidence is, not certainty it is the right call. Effort estimates are
coarser here; say so. Selected direction findings usually become a design or
spike plan, not a build-everything plan.

---

## Finding format

Every finding, from every category and every subagent, comes back in this shape:

```markdown
### [CATEGORY-NN] Short imperative title

- **Evidence**: `path/file.py:123` — one sentence on what is there. (Repeat per
  location; 2–5 strongest, note "and ~N similar sites" if widespread.)
- **Impact**: What goes wrong, concretely. "Every enrichment run refetches every
  season of every show", not "suboptimal".
- **Effort**: S (hours) / M (a day-ish) / L (multi-day) — for the *fix*,
  including tests.
- **Risk**: What the fix could break; LOW/MED/HIGH plus one line why.
- **Confidence**: HIGH (read the code, certain) / MED (strong signal, needs
  verification) / LOW (smell, needs investigation). LOW-confidence findings get
  an "investigate" plan, not a "fix" plan.
- **Fix sketch**: 1–3 sentences. Not the plan — just enough to judge effort.
```

## Prioritization rubric

Order by **leverage = impact ÷ effort, discounted by confidence and fix-risk**.
Tiebreakers:

1. Anything that unblocks other findings (a verification baseline,
   characterization tests) floats up.
2. HIGH-confidence security findings float above equivalent-leverage
   non-security findings.
3. Prefer findings with a clean verification story — `just check` either passes
   or it doesn't, and executors succeed at those.
4. Anything touching the library's *data* outranks anything touching its
   presentation, because a wrong number is invisible and a wrong colour is not.
5. "Not worth doing" is a valid verdict. Record it with one line of reasoning so
   nobody re-audits it.
