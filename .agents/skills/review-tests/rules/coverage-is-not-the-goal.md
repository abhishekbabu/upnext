# 8. The floor is not a target

Coverage is gated at 95%. The number exists to catch a module nobody tested at
all, not to be maximised. A test written to move the percentage is worse than
the uncovered line it replaces: it has to be read, maintained and understood by
everyone who comes after, and it protects nothing.

## The shape this takes

```python
def test_title_row_fields(library: Library) -> None:
    row = library.title(title_id)
    assert row.id is not None
    assert row.name is not None
    assert row.kind is not None
```

Every line of `_title_row` runs. Nothing is asserted that could be wrong.
Rename any field and this still passes; drop a column and it still passes.

## What to do with a genuinely uncovered line

Three honest answers, in order of preference:

1. **It has a behavior worth protecting** — write the test that describes the
   behavior, not the one that reaches the line.
2. **It is unreachable** — delete it. An uncoverable branch is usually a branch
   that cannot happen, and the coverage report is telling you so.
3. **It is a shell that cannot be exercised without a terminal or a server** —
   exclude it in `pyproject.toml` with the reason in the comment, as the
   `exclude_lines` entries already do for `Protocol` bodies.

## What to flag

- A test whose assertions cannot fail (`is not None` on a required field,
  `assert result` on something that always returns a truthy value)
- A test that constructs an object and asserts the constructor worked
- A test added in the same commit as the code it covers, asserting nothing the
  code's own name does not already say
- Conversely: a *drop* in coverage is not automatically a finding. Deleting a
  worthless test is a good change even though the percentage falls.
