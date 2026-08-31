# 5. One reason to fail

A test that checks five things reports the first failure and hides the rest, and
its name cannot describe what it covers — which is why such tests end up called
`test_the_library` or `test_the_happy_path`.

## Reject

```python
def test_the_library(library: Library) -> None:
    row = library.title(title_id)
    assert row.episodes_watched == 8
    assert row.status is Status.WATCHING
    assert library.stats()["watches"] == 12
    assert library.up_next()[0]["episode_number"] == 9
    assert len(library.episodes(title_id)) == 24
```

When this fails on line 3 you learn nothing about lines 4–7, and the name
promises the whole repository works.

## Keep

```python
def test_specials_are_neither_progress_nor_a_disagreement() -> None:
def test_up_next_is_the_lowest_unwatched_episode_and_skips_specials() -> None:
def test_a_rewatch_is_one_episode_and_two_viewings() -> None:
```

## Shared setup, separate assertions

Splitting does not mean repeating setup. Hoist it into a helper or fixture —
`tests/test_unmatched.py` does exactly this with its `a_show` and `enrich`
helpers, and `flat_show` for the flattened-catalog cases.

## Where several assertions are one behavior

Asserting three fields of one returned object is one behavior if the behavior is
"this row is built correctly from this input". The signal is whether the
assertions can fail *independently for different reasons*:

```python
assert (row.episodes_watched, row.unmatched_watched, row.total_episodes) == (4, 1, 3)
```

Those three share a cause — one counting query. A progress count, a watch total
and an up-next result do not.
