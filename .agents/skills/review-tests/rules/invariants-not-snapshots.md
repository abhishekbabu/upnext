# 3. Test invariants, not snapshots

A hardcoded copy of today's output tests that nothing changed, not that the
rule holds. It goes stale the first time a legitimate value changes, and the fix
is always to paste the new value in — which teaches everyone that a red test
means "update the expected value", the exact reflex you do not want.

This repo has already been bitten by it. The live TMDB test pinned Friends at
236 episodes; TMDB reports 228, because it excludes specials and counts each
double-length episode once. The number was never upnext's to assert.

## Reject

```python
def test_friends_has_236_episodes(client: TMDBClient) -> None:
    assert title_from_show(client.show(1668)).total_episodes == 236
```

## Keep

```python
def test_fetching_a_show_brings_back_its_episodes(client: TMDBClient) -> None:
    show = client.fetch_show(1668)
    assert show.title.total_episodes is not None
    assert show.title.total_episodes > 200
    # Season 0 is carried through, so specials the user logged keep their rows.
    assert {episode.season_number for episode in show.episodes} >= {0, 1, 10}
```

The name, the year and the tvdb_id stay exact in that test, because those are
identity: if they change, something is genuinely wrong.

## When a literal is right

Pin the exact value when the value itself is the contract with an outside
system or with a reader: a wire format, an episode code, a rendered date.
`"S01E04"` in an `episodeCode` test is the specification, not a snapshot.
