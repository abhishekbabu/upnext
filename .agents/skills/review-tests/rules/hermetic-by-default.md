# 7. Hermetic by default

The default suite must run with no network, no TMDB key, and nothing written
outside `tmp_path`. That is what makes it usable in a pre-commit hook and
identical in CI on a runner that has never heard of your `.env`. A single test
that reaches out makes the whole suite fail on a plane, flake on a rate limit,
or depend on whose laptop it runs on.

Three things hold the line, and all three belong in a review:

**`_isolate_from_local_env` (autouse).** `settings.py` finds `.env` by absolute
path, on purpose, so that `upnext` works from any directory — which means a test
calling `load_settings()` would otherwise read the real key off the developer's
disk and not off CI's. The fixture clears it, and points `db_path` away from
`~/.upnext/library.db`.

**The `library` fixture.** A real `Library` over `:memory:`. Real SQL, real
constraints, no file. A test that needs a file on disk takes `tmp_path`.

**The `integration` marker.** Declared in `pyproject.toml` and deselected by
`addopts = "-m 'not integration'"`. Anything touching TMDB carries it. That
marker is the only sanctioned way to reach the network.

## Reject

```python
def test_enrichment_resolves_a_show() -> None:
    catalog = TMDBClient(load_settings().tmdb_api_key)   # real key, real HTTP
    conn = connect(Path.home() / ".upnext" / "library.db")   # the real library
```

## Keep

```python
def test_enrichment_matches_the_watches_that_were_waiting(library: Library) -> None:
    enrich(library, title_id, total=2, episodes=[(1, 1), (1, 2)])


@pytest.mark.integration
def test_a_tvdb_id_from_the_export_resolves_to_the_right_show(client: TMDBClient) -> None:
    """Deselected by default; opt in with `just test-integration`."""
```

## What to flag

- A `TMDBClient` built in a test body without a fake `session`
- `connect()` on anything but `":memory:"` or a path under `tmp_path`
- `load_settings()` relied on for a value the test did not set
- A test that hits TMDB and is *not* marked `integration`
- A test marked `integration` that does not need to be — the marker means it is
  never run by `just check`, so an over-marked test is an unrun test
