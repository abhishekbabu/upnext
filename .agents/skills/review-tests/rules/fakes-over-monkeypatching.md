# 6. Use the fakes, not monkeypatch

The use cases in `application/` take their collaborators as arguments precisely
so a test can hand them a stand-in. `ScoutEngine`-style defaults do not exist
here on purpose: `enrich(catalog, library, titles)` names both ports, and
`bootstrap` is the only module that turns one into a `TMDBClient`.

So a test supplies a fake. `tests/conftest.py` holds one per port — the
`library` fixture over the real SQLite repository at `:memory:`, and a
`FakeCatalog` implementing `Catalog` in domain types.

Monkeypatching reaches around that design. It binds the test to the import path
of the thing it patches, so moving a module breaks tests that never named it; it
leaks when a patch target is imported under two names; and it hides the fact
that the collaborator was always meant to be injected.

## Reject

```python
def test_enrichment_fills_a_title(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "upnext.adapters.outbound.catalog.tmdb.TMDBClient.fetch_show",
        lambda self, _id: CatalogShow(title=Title(name="Friends")),
    )
```

## Keep

```python
def test_enrichment_fills_the_title_and_every_episode(library: Library) -> None:
    assert enrich_title(FakeCatalog(found=CatalogMatch(catalog_id=1668)), library, title) is True
```

## One fake per port

A fake belongs in `conftest.py`, once. A second fake for the same port is how
two tests come to disagree about what the real thing does — one returns
`CatalogMatch`, the next returns a dict, and a change to the port fixes only the
half somebody remembered. If a test needs behavior the fake lacks, extend the
fake; do not define a rival beside it.

Fakes here are plain classes implementing the `Protocol`. No `unittest.mock`, no
`autospec`: a `Protocol` is already the contract, and a fake that does not
satisfy it fails the typecheck, which is the point.

## Where monkeypatch is still right

Process-level state that is not injected, and is not supposed to be: the
environment, the clock, module globals. `_isolate_from_local_env` in
`conftest.py` is the model — it points `UPNEXT_TMDB_API_KEY` and the database at
somewhere harmless, and neither has a keyword to hand in. Patching
`bootstrap.build_catalog` in a CLI test is the same case: the composition root
is deliberately a module-level function, and the CLI's job is to call it.

## What to flag

- A `monkeypatch.setattr` on a class or function reachable through a port
- A second fake for a port `conftest.py` already covers
- A fake that returns the vendor's payload shape rather than domain types — that
  is testing the adapter's translation twice, and testing it in the wrong place
