# 11. Logic in `lib/`, rendering only where it is the behavior

Two kinds of front-end test live here and the line between them matters.

**`web/src/lib/format.test.ts` is the first kind.** Pure functions that take
values and return values: `progressOf`, `episodeCode`, `shortDate`, `poster`.
Every rule about how the library reads lives in `lib/` and is tested by calling
it. Rendering a component to reach a calculation buried inside it is slow,
couples the assertion to markup, and fails when a class name changes.

**`web/src/panels/panels.test.tsx` is the second kind**, and it earns its place
by testing what only exists once rendered: that a loading state gives way to
rows, that an empty result says so rather than showing an empty grid, that a
failed request reaches the screen instead of a blank page, that a poster with no
artwork falls back to initials. A typecheck cannot prove any of those.

## Reject

```tsx
it("formats the progress", () => {
  render(<Library />)
  expect(screen.getByText("228 / 228")).toBeTruthy()   // testing progressOf through the DOM
})
```

## Keep

```ts
it("keeps the unmatched count beside a measured share", () => {
  expect(progressOf({ episodes_watched: 228, unmatched_watched: 8, total_episodes: 228 }))
    .toEqual({ kind: "measured", watched: 228, total: 228, share: 1, unmatched: 8 })
})
```

```tsx
it("says so when nothing is in progress, rather than showing an empty grid", async () => {
  stubFetch({ "/api/config": CONFIG, "/api/up-next": [] })
  draw(<UpNext />)
  expect(await screen.findByText("Nothing in progress")).toBeTruthy()
})
```

## What to flag

- A `.test.tsx` that renders only to reach a calculation — extract it to `lib/`
- Logic inside a component or hook with no exported, testable seam
- Assertions on class names or Tailwind utilities: styling is not behavior, and
  `AGENTS.md` already forbids raw palette utilities, so the token is the
  contract and it is checked by review, not by a unit test
- A stubbed `fetch` that answers any path — the stub in `panels.test.tsx` throws
  on an unstubbed one deliberately, so a panel that starts calling a new
  endpoint fails loudly instead of hanging
- A locale-dependent assertion with no locale pinned. `toLocaleDateString`
  follows the runtime, so `shortDate` takes the locale as an argument and every
  test passes one. Without it the suite passes in London and fails in New York.
