/**
 * The panels, rendered.
 *
 * A typecheck proves the shapes line up; it cannot prove a shelf renders, that
 * a loading state gives way to rows, or that a failure reaches the screen
 * instead of a blank page. These do, against a stubbed `fetch` — no server, no
 * network, no database.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { type QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createQueryClient } from "@/lib/queries";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Airing, AiringItem, Config, Stats, TitleDetail, TitleSummary, UpNextItem } from "@/lib/api";
import { Library } from "@/panels/Library";
import { Stats as StatsPanel } from "@/panels/Stats";
import { Title as TitlePanel } from "@/panels/Title";
import { UpNext } from "@/panels/UpNext";

const CONFIG: Config = { image_base: "https://image.tmdb.org/t/p" };

const FRIENDS: TitleSummary = {
  id: 1,
  name: "Friends",
  year: 1994,
  poster_path: "/friends.jpg",
  total_episodes: 228,
  status: "completed",
  episodes_watched: 228,
  unmatched_watched: 0,
  enriched_at: "2026-08-31T00:00:00+00:00",
};

const UNENRICHED: TitleSummary = {
  ...FRIENDS,
  id: 2,
  name: "Armor Wars",
  poster_path: null,
  total_episodes: null,
  status: "watchlist",
  episodes_watched: 0,
  unmatched_watched: 3,
  enriched_at: null,
};

const NEXT_UP: UpNextItem = {
  title_id: 1,
  name: "Avatar: The Last Airbender",
  poster_path: "/avatar.jpg",
  episode_id: 44,
  season_number: 2,
  episode_number: 2,
  episode_name: "A Fight, Once Begun",
  last_watched_at: "2026-07-06 05:27:04",
};

const TODAY = "2099-01-01";

const LASSO: AiringItem = {
  title_id: 7,
  name: "Ted Lasso",
  poster_path: "/lasso.jpg",
  episode_id: 901,
  season_number: 4,
  episode_number: 5,
  episode_name: "Riches of Embarrassment",
  air_date: TODAY,
};

/** Two episodes a week apart, so they group as two days rather than one. */
const AIRING: Airing = {
  today: TODAY,
  episodes: [LASSO, { ...LASSO, episode_id: 902, episode_number: 6, episode_name: null, air_date: "2099-01-08" }],
};

const NOTHING_AIRING: Airing = { today: TODAY, episodes: [] };

const STATS: Stats = {
  watches: 4471,
  distinct_episodes: 4240,
  titles_watched: 123,
  first_watch: "2017-02-18 20:17:55",
  last_watch: "2026-07-06 05:27:04",
  known_minutes: 150_540,
  by_status: { watching: 74, stopped: 51, completed: 27, watchlist: 9 },
};

/** A route that fails, with the body the server would send. */
class Fails {
  constructor(
    readonly body: unknown = {},
    readonly status = 500,
  ) {}
}

/** Answer each endpoint the panels call, and fail loudly on one nobody stubbed. */
function stubFetch(routes: Record<string, unknown>) {
  vi.stubGlobal("fetch", (input: string) => {
    const path = new URL(input, "http://localhost").pathname;
    const body = routes[path] ?? (path === "/api/config" ? CONFIG : undefined);
    if (body === undefined) throw new Error(`No stub for ${path}`);
    if (body instanceof Fails) {
      return Promise.resolve({
        ok: false,
        status: body.status,
        statusText: body.status === 422 ? "Unprocessable Entity" : "Internal Server Error",
        json: () => Promise.resolve(body.body),
      } as Response);
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve(body) } as Response);
  });
}

function draw(ui: React.ReactNode, at = "/") {
  client = createQueryClient();
  return render(
    <MemoryRouter initialEntries={[at]}>
      <QueryClientProvider client={client}>
        <Routes>
          <Route path="/titles/:id" element={ui} />
          <Route path="*" element={ui} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

function drawTitle(detail: TitleDetail) {
  stubFetch({ "/api/titles/1": detail });
  return draw(<TitlePanel />, "/titles/1");
}

let client: QueryClient;

/** An absent section proves nothing until the request behind it has settled. */
async function settled(key: string) {
  await waitFor(() => expect(client.getQueryState([key])?.status).toMatch(/^(success|error)$/));
}

afterEach(() => vi.unstubAllGlobals());

describe("UpNext", () => {
  it("shows the next episode of each show in progress", async () => {
    stubFetch({ "/api/up-next": [NEXT_UP], "/api/airing": NOTHING_AIRING });
    draw(<UpNext />);

    expect(await screen.findByText("Avatar: The Last Airbender")).toBeTruthy();
    expect(screen.getByText("S02E02")).toBeTruthy();
    expect(screen.getByText("A Fight, Once Begun")).toBeTruthy();
    expect(screen.getByRole("link")).toHaveProperty("href", expect.stringContaining("/titles/1"));
  });

  it("says so when nothing is in progress, rather than showing an empty grid", async () => {
    stubFetch({ "/api/up-next": [], "/api/airing": NOTHING_AIRING });
    draw(<UpNext />);

    expect(await screen.findByText("Nothing in progress")).toBeTruthy();
  });

  it("lists what is coming, grouped by the day it airs", async () => {
    stubFetch({ "/api/up-next": [NEXT_UP], "/api/airing": AIRING });
    draw(<UpNext />);

    expect(await screen.findByText("Airing next")).toBeTruthy();
    // Two episodes a week apart are two headings, not one list of two rows.
    expect(screen.getAllByRole("heading", { level: 3 })).toHaveLength(2);
    expect(screen.getByText("S04E05")).toBeTruthy();
    expect(screen.getByText("Riches of Embarrassment")).toBeTruthy();
  });

  it("lists every episode of a season that lands at once", async () => {
    const sameDay = {
      today: TODAY,
      episodes: [1, 2, 3].map((n) => ({
        ...LASSO,
        episode_id: 950 + n,
        episode_number: n,
        episode_name: `Episode ${n}`,
        air_date: "2099-02-01",
      })),
    };
    stubFetch({ "/api/up-next": [NEXT_UP], "/api/airing": sameDay });
    draw(<UpNext />);

    // One day, three rows — not one row claiming three episodes.
    expect(await screen.findByText("S04E01")).toBeTruthy();
    expect(screen.getByText("S04E03")).toBeTruthy();
    expect(screen.getAllByRole("heading", { level: 3 })).toHaveLength(1);
    expect(screen.getAllByText("Ted Lasso")).toHaveLength(3);
  });

  it("leaves the calendar out entirely when nothing is scheduled", async () => {
    // An "Airing next" heading over blank space reads as a failure. Having
    // nothing coming is ordinary — most of a library is finished shows.
    stubFetch({ "/api/up-next": [NEXT_UP], "/api/airing": NOTHING_AIRING });
    draw(<UpNext />);

    expect(await screen.findByText("Avatar: The Last Airbender")).toBeTruthy();
    await settled("airing");
    expect(screen.queryByText("Airing next")).toBeNull();
  });

  it("keeps the shelf when only the calendar fails", async () => {
    // The page is for the shelf. A calendar that will not load is not worth
    // replacing it with an error.
    stubFetch({ "/api/up-next": [NEXT_UP], "/api/airing": new Fails() });
    draw(<UpNext />);

    expect(await screen.findByText("Avatar: The Last Airbender")).toBeTruthy();
    await settled("airing");
    expect(screen.queryByText("Airing next")).toBeNull();
  });

  it("shows the server's own words when the request fails", async () => {
    stubFetch({ "/api/up-next": new Fails({ detail: "the library is locked" }), "/api/airing": NOTHING_AIRING });
    draw(<UpNext />);

    expect(await screen.findByRole("alert")).toHaveProperty("textContent", expect.stringContaining("locked"));
  });

  it("shows the status line, not a list, when validation fails", async () => {
    // FastAPI's 422 carries `detail` as a list of objects.
    stubFetch({ "/api/up-next": new Fails({ detail: [{ msg: "bad" }] }, 422), "/api/airing": NOTHING_AIRING });
    draw(<UpNext />);

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("422 Unprocessable Entity");
    expect(alert.textContent).not.toContain("[object Object]");
  });
});

describe("Library", () => {
  it("renders progress against the catalog count", async () => {
    stubFetch({ "/api/titles": [FRIENDS] });
    draw(<Library />);

    expect(await screen.findByText("Friends")).toBeTruthy();
    expect(screen.getByText("228 / 228")).toBeTruthy();
    expect(screen.getByRole("progressbar").getAttribute("aria-valuenow")).toBe("100");
  });

  it("shows a bare count, and no bar, for a title TMDB has not been asked about", async () => {
    // The denominator is what a bar needs. Without one, claiming 100% because
    // every known episode is watched would be a lie about an unenriched show.
    stubFetch({ "/api/titles": [UNENRICHED] });
    draw(<Library />);

    expect(await screen.findByText("3 watched · not enriched")).toBeTruthy();
    expect(screen.queryByRole("progressbar")).toBeNull();
  });

  it("counts without measuring when TMDB lists no total", async () => {
    stubFetch({ "/api/titles": [{ ...FRIENDS, episodes_watched: 12, total_episodes: null }] });
    draw(<Library />);

    expect(await screen.findByText("12 watched")).toBeTruthy();
    expect(screen.queryByRole("progressbar")).toBeNull();
  });

  it("never draws one episode short as finished", async () => {
    stubFetch({ "/api/titles": [{ ...FRIENDS, episodes_watched: 227 }] });
    draw(<Library />);

    const bar = await screen.findByRole("progressbar", { name: "Friends" });
    expect(bar.getAttribute("aria-valuenow")).toBe("99");
    expect(bar.firstElementChild?.className).not.toContain("bg-ok");
  });

  it("says which statuses have nothing, rather than suggesting an import", async () => {
    stubFetch({ "/api/titles": [] });
    draw(<Library />, "/library?status=stopped");

    expect(await screen.findByText("Nothing marked stopped")).toBeTruthy();
    expect(screen.queryByText(/just import/)).toBeNull();
  });

  it("draws no bar for a show whose numbering TMDB does not share", async () => {
    // Sidemen Sundays: 320 watched, none on TMDB's 461-episode list. A 0% bar
    // would be true and would read as "not started".
    stubFetch({
      "/api/titles": [{ ...FRIENDS, episodes_watched: 0, unmatched_watched: 320, total_episodes: 461 }],
    });
    draw(<Library />);

    expect(await screen.findByText("320 watched · none on TMDB’s list")).toBeTruthy();
    expect(screen.queryByRole("progressbar")).toBeNull();
  });

  it("keeps the search in the address, so going back finds it", async () => {
    stubFetch({ "/api/titles": [FRIENDS, UNENRICHED] });
    draw(<Library />, "/library?q=armor");

    expect(await screen.findByText("Armor Wars")).toBeTruthy();
    expect(screen.queryByText("Friends")).toBeNull();
    expect(screen.getByRole("searchbox")).toHaveProperty("value", "armor");
  });

  it("shows initials when TMDB no longer serves a poster", async () => {
    stubFetch({ "/api/titles": [FRIENDS] });
    const { container } = draw(<Library />);

    await waitFor(() => expect(container.querySelector("img")).not.toBeNull());
    fireEvent.error(container.querySelector("img")!);
    expect(await screen.findByText("F")).toBeTruthy();
  });

  it("falls back to initials when the artwork CDN cannot be found", async () => {
    stubFetch({ "/api/titles": [FRIENDS], "/api/config": new Fails() });
    draw(<Library />);

    await screen.findByText("Friends");
    await settled("config");
    expect(screen.getByText("F")).toBeTruthy();
  });

  it("falls back to initials when a title has no poster", async () => {
    stubFetch({ "/api/titles": [UNENRICHED] });
    draw(<Library />);

    await screen.findByText("Armor Wars");
    expect(screen.getByText("AW")).toBeTruthy();
    expect(screen.queryByRole("img")).toBeNull();
  });
});

describe("Stats", () => {
  it("reads the runtime as a floor and the range as dates", async () => {
    stubFetch({ "/api/stats": STATS });
    draw(<StatsPanel />);

    await waitFor(() => expect(screen.getByText("4,240")).toBeTruthy());
    expect(screen.getByText(/2017 — .*2026/)).toBeTruthy();
    expect(screen.getByText("At least")).toBeTruthy();
    expect(screen.getByText("2,509 hours")).toBeTruthy();
    expect(screen.getByText("74")).toBeTruthy();
  });
});

describe("Title", () => {
  const DETAIL: TitleDetail = {
    ...FRIENDS,
    unmatched_watched: 1,
    overview: "Six friends.",
    air_status: "Ended",
    rating: 10,
    episodes: [
      {
        id: 1,
        season_number: 1,
        episode_number: 1,
        name: "The One Where It Begins",
        air_date: "1994-09-22",
        watch_count: 2,
      },
      {
        id: 2,
        season_number: 0,
        episode_number: 1,
        name: "The One With The Reunion",
        air_date: "2004-05-06",
        watch_count: 1,
      },
    ],
    unmatched: [{ season_number: 6, episode_number: 25, watch_count: 1, last_watched_at: "2018-06-01 00:00:00" }],
  };

  it("accounts for the viewings TMDB's list does not contain", async () => {
    drawTitle(DETAIL);

    expect(await screen.findByText("Also watched")).toBeTruthy();
    // Named concretely, so the claim is checkable rather than just a number.
    expect(screen.getByText(/S06E25/)).toBeTruthy();
  });

  it("keeps specials visible and says why they are outside the count", async () => {
    // TMDB's number_of_episodes excludes season 0, so a watched special is not
    // progress — but it is still watched, and still listed.
    drawTitle(DETAIL);

    expect(await screen.findByText("Specials")).toBeTruthy();
    expect(screen.getByText("The One With The Reunion")).toBeTruthy();
    expect(screen.getByText(/plus 1 special, which TMDB counts separately/)).toBeTruthy();
  });

  it("shows a rewatch as a count rather than a tick", async () => {
    drawTitle(DETAIL);
    expect(await screen.findByText("×2")).toBeTruthy();
  });

  it("does not call viewings TMDB was never asked about a disagreement", async () => {
    drawTitle({ ...DETAIL, enriched_at: null, total_episodes: null, episodes: [] });

    await screen.findByText(/Run `just enrich` to match them/);
    expect(screen.queryByText("Also watched")).toBeNull();
  });

  it("says nothing about unmatched viewings when there are none", async () => {
    drawTitle({ ...DETAIL, unmatched_watched: 0, unmatched: [] });

    await screen.findByText("The One Where It Begins");
    expect(screen.queryByText("Also watched")).toBeNull();
  });
});

describe("a show numbered wholly differently", () => {
  /** Sidemen Sundays: 320 viewings, none on TMDB's list, all needing somewhere to go. */
  const MANY = Array.from({ length: 60 }, (_, i) => ({
    season_number: 2018,
    episode_number: i + 1,
    watch_count: 1,
    last_watched_at: "2021-12-26 00:00:00",
  }));

  it("folds a long list behind a count rather than burying the page", async () => {
    drawTitle({
      ...FRIENDS,
      episodes_watched: 0,
      unmatched_watched: 60,
      total_episodes: 461,
      overview: null,
      air_status: null,
      rating: null,
      episodes: [],
      unmatched: MANY,
    });

    // The headline is the count and the reason, not three hundred chips.
    expect(await screen.findByText(/none of them on TMDB/)).toBeTruthy();
    expect(screen.getByText("Show all 60")).toBeTruthy();
    // No bar: a 0% one beside 60 watched episodes reads as "not started".
    expect(screen.queryByRole("progressbar")).toBeNull();
  });
});
