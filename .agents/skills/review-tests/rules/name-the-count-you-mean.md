# 9. Name the count you mean

This library counts three different things, and they are easy to confuse
because they are all "how much did I watch":

| Count | Where | What it is |
|---|---|---|
| `watches` | `stats()` | viewings, so a rewatch is two |
| `episodes_watched` | `TitleRow` | distinct episodes, specials excluded, **matched to TMDB's list** — pairs with `total_episodes` |
| `unmatched_watched` | `TitleRow` | distinct episodes TMDB's list does not contain |

Every one of this repo's counting bugs was a confusion between two of them.
`episodes_watched` once included specials while `total_episodes` excluded them,
and INVINCIBLE read 33 of 32. It once included episodes TMDB had never listed,
and a complete Friends read 236 of 228.

## Reject

```python
def test_the_count_is_right(library: Library) -> None:
    assert library.title(title_id).episodes_watched == 9
```

Nine of what? A reader cannot tell whether the special counted, whether a
rewatch counted twice, or whether an episode TMDB does not list is in there.

## Keep

```python
def test_specials_are_neither_progress_nor_a_disagreement(library: Library) -> None:
    row = library.title(title_id)
    assert (row.episodes_watched, row.unmatched_watched, row.total_episodes) == (1, 0, 1)
    # Still stored, still shown, still a viewing.
    assert len(library.episodes(title_id)) == 2
    assert library.stats()["episodes_watched"] == 2
```

Asserting the pair together is what makes the claim legible, and asserting the
library-wide total alongside is what stops "excluded from progress" quietly
becoming "excluded from everything".

## What to flag

- A single-number assertion on `episodes_watched` where the special or unmatched
  case is what the test is actually about
- A test that changes a count expectation without saying which of the three
  moved and why
- Progress asserted without `total_episodes` beside it — the numerator alone
  cannot show that the pair agrees
- `unmatched_watched` asserted without `enriched_at` in view: before enrichment
  everything is unmatched because nothing has been asked, which is the opposite
  statement to a disagreement
