# 1. Never test the framework

Test what this app decided, not what a dependency already guarantees. Pydantic
validates, FastAPI routes, SQLite stores what you put in it and `dict` keeps its
keys — none of that is this repo's behavior, and a test asserting it fails only
when a dependency upgrade changes something the upgrade notes already told you.

## Reject

```python
def test_a_title_row_has_a_name() -> None:
    row = TitleSummary(id=1, kind=Kind.SHOW, name="Friends")
    assert row.name == "Friends"            # pydantic assigning a field


def test_the_api_returns_json() -> None:
    assert client.get("/api/titles").headers["content-type"] == "application/json"


def test_an_insert_is_readable_afterwards(library: Library) -> None:
    library.upsert_title(Title(name="Friends"))
    assert library.count_titles() == 1      # SQLite, not upnext
```

## Keep

```python
def test_an_import_never_erases_enriched_columns() -> None:
    """A second import knows only what the export knew, and must not wipe the
    overview and artwork a previous enrichment resolved."""


def test_a_title_is_matched_by_tvdb_id_not_duplicated() -> None:
    """Widest identifier first, so a title that gains a tmdb_id during
    enrichment is still the same row on the next import."""
```

The first group tests pydantic, Starlette and SQLite. The second tests rules
this repo argued itself into, recorded in `AGENTS.md`, and would silently lose
in a refactor.

## The test

Ask: *if I deleted this app's code and kept the dependencies, would this test
still pass?* If yes, it is testing the framework. Delete it.
