# 2. Assert behavior, not implementation

A test should describe what the caller observes. Asserting on which
collaborator was called, in what order, or how many times, welds the test to
today's structure — so a refactor that preserves every observable behavior
still turns the suite red, and the suite stops being a safety net and becomes a
tax on changing anything.

## Reject

```python
def test_enrichment_fetches_the_show() -> None:
    enrich_title(catalog, library, title)
    assert catalog.fetch_show_calls == 1          # an internal call count
    assert library.upsert_episode_calls == 24
```

## Keep

```python
def test_enrichment_fills_the_title_and_every_episode(library: Library) -> None:
    enrich_title(FakeCatalog(found=CatalogMatch(catalog_id=1668)), library, title)

    row = library.title(title.id)
    assert (row.tmdb_id, row.air_status, row.total_episodes) == (1668, "Ended", 236)
```

## The exception that is not one

Sometimes the call *is* the behavior. Resolution must not search when it has an
identity, and "did not search" is only observable as an absence:

```python
def test_a_tvdb_id_resolves_without_searching(library: Library) -> None:
    catalog = FakeCatalog(found=CatalogMatch(catalog_id=1668))
    assert resolve_show(catalog, imported(library, tvdb_id=79168)).catalog_id == 1668
    assert catalog.searched == []
```

That is legitimate: not guessing *is* the contract, and a caller notices a wrong
match. The difference is whether the caller would notice. A caller notices an
avoided name search; a caller does not notice which private helper built the row.
