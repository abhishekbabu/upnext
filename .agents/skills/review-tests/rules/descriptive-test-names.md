# 4. The name is the specification

A test name is read far more often than the body — in failure output, in a diff,
in a suite listing. It should say the scenario and the expected outcome, so a
failure is legible before anyone opens the file.

This repo already sets the bar. From `tests/test_unmatched.py`:

```python
def test_recording_a_watch_invents_no_episode() -> None:
def test_a_watch_the_catalog_has_no_episode_for_stays_unmatched() -> None:
def test_the_ordering_must_agree_with_what_already_matched() -> None:
def test_a_watch_the_export_could_not_number_counts_as_viewing_only() -> None:
```

Read those four together and you have the matching rules without opening
`library.py`.

## Reject

```python
def test_link() -> None:                   # no scenario, no outcome
def test_library_2() -> None:              # says nothing at all
def test_error() -> None:                  # which error, and then what?
def test_it_works() -> None:               # what is "works"?
```

## Rename to

```python
def test_matching_is_exact_and_never_guesses() -> None:
def test_a_year_labelled_season_is_aliased_to_the_one_that_aired_then() -> None:
def test_a_folder_that_is_not_an_export_is_refused() -> None:
```

## The test

Read the name aloud without the `test_` prefix. If it is not a claim that can be
true or false, it is not a name — it is a label.
