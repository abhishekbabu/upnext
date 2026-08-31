# 10. A migration test starts from the old shape

`migrate()` runs on every `connect()`, and its whole job is to fix databases
that `schema.sql` cannot reach — `CREATE TABLE IF NOT EXISTS` does nothing to a
table that already exists. So a migration tested against a database built by the
current schema tests nothing: the migration finds its work already done and
returns immediately.

The test has to construct the *old* shape by hand.

## Reject

```python
def test_the_reshape(tmp_path: Path) -> None:
    conn = connect(tmp_path / "library.db")     # already the new shape
    migrate(conn)
    assert "source_season" in columns_of(conn, "watches")
```

This passes before the migration is written.

## Keep

```python
def test_an_existing_library_is_reshaped_without_a_re_import(tmp_path: Path) -> None:
    old = sqlite3.connect(tmp_path / "old.db")
    old.executescript(
        """
        CREATE TABLE watches (
            id INTEGER PRIMARY KEY, title_id INTEGER, episode_id INTEGER, ...
        );
        INSERT INTO episodes (id, title_id, season_number, episode_number, tmdb_id)
             VALUES (11, 1, 6, 25, NULL);      -- the invented row
        INSERT INTO watches (title_id, episode_id, watched_at) VALUES (1, 11, '...');
        """
    )
    migrate(old)

    # Both viewings survive. The invented row does not.
    assert count(old, "watches") == 2
    assert count(old, "episodes") == 1
```

## Two things every migration test needs

**Nothing is lost.** Row counts for every table the migration touches, before
and after. This repo's migrations delete rows and rebuild a table; the test that
matters is the one proving the viewings outlived both.

**It is safe to run twice.** `migrate()` runs on every connect, so a test that
connects, writes, closes and reconnects is not optional — it is the only thing
standing between an idempotent step and one that corrupts on the second open.

## What to flag

- A migration test whose fixture came from `connect()` or `schema.sql`
- A migration test with no before/after row counts
- A migration with no second-run test
- A destructive step (`DROP`, `DELETE`, `ALTER ... DROP COLUMN`) whose test does
  not assert what survived it
