/**
 * The panels, rendered.
 *
 * A typecheck proves the shapes line up; it cannot prove a shelf renders, that
 * a loading state gives way to rows, or that a failure reaches the screen
 * instead of a blank page. These do, against a stubbed `fetch` — no server, no
 * network, no database.
 */

import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AiringItem, Stats, TitleSummary, UpNextItem } from "@/lib/api";
import { Library } from "@/panels/Library";
import { Stats as StatsPanel } from "@/panels/Stats";
import { Title as TitlePanel } from "@/panels/Title";
import { UpNext } from "@/panels/UpNext";

const CONFIG = { image_base: "https://image.tmdb.org/t/p" };

const FRIENDS: TitleSummary = {
  id: 1,
  kind: "show",
  name: "Friends",
  year: 1994,
  poster_path: "/friends.jpg",
  air_status: "Ended",
  total_episodes: 228,
  status: "completed",
  is_favorite: true,
  rating: 10,
  episodes_watched: 228,
  unmatched_watched: 0,
  enriched_at: "2026-08-31T00:00:00+00:00",
  last_watched_at: "2021-04-23 00:23:28",
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
  rating: null,
};

const NEXT_UP: UpNextItem = {
  title_id: 1,
  name: "Avatar: The Last Airbender",
  kind: "show",
  year: 2024,
  poster_path: "/avatar.jpg",
  episode_id: 44,
  season_number: 2,
  episode_number: 2,
  episode_name: "A Fight, Once Begun",
  air_date: "2026-06-25",
  still_path: null,
  last_watched_at: "2026-07-06 05:27:04",
};

/** Far enough out that the calendar keeps treating it as upcoming. */
const LASSO: AiringItem = {
  title_id: 7,
  name: "Ted Lasso",
  kind: "show",
  year: 2020,
  poster_path: "/lasso.jpg",
  episode_id: 901,
  season_number: 4,
  episode_number: 5,
  episode_name: "Riches of Embarrassment",
  air_date: "2099-01-01",
  still_path: null,
  last_watched_at: "2023-01-01 00:00:00",
};

/** Two episodes a week apart, so they group as two days rather than one. */
const AIRING: AiringItem[] = [
  LASSO,
  { ...LASSO, episode_id: 902, episode_number: 6, episode_name: null, air_date: "2099-01-08" },
];

const STATS: Stats = {
  watches: 4471,
  episodes_watched: 4240,
  titles_watched: 123,
  first_watch: "2017-02-18 20:17:55",
  last_watch: "2026-07-06 05:27:04",
  known_minutes: 150_540,
  by_status: { watching: 74, stopped: 51, completed: 27, watchlist: 9 },
};

/** Answer each endpoint the panels call, and fail loudly on one nobody stubbed. */
function stubFetch(routes: Record<string, unknown>) {
  vi.stubGlobal("fetch", (input: string) => {
    const path = new URL(input, "http://localhost").pathname;
    const body = routes[path];
    if (body === undefined) throw new Error(`No stub for ${path}`);
    return Promise.resolve({ ok: true, json: () => Promise.resolve(body) } as Response);
  });
}

function draw(ui: React.ReactNode) {
  // retry: false so a stubbed failure surfaces immediately rather than after
  // three backoffs the test would have to wait out.
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}>{ui}</QueryClientProvider>
    </MemoryRouter>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("UpNext", () => {
  it("shows the next episode of each show in progress", async () => {
    stubFetch({ "/api/config": CONFIG, "/api/up-next": [NEXT_UP], "/api/airing": [] });
    draw(<UpNext />);

    expect(await screen.findByText("Avatar: The Last Airbender")).toBeTruthy();
    expect(screen.getByText("S02E02")).toBeTruthy();
    expect(screen.getByText("A Fight, Once Begun")).toBeTruthy();
    expect(screen.getByRole("link")).toHaveProperty("href", expect.stringContaining("/titles/1"));
  });

  it("says so when nothing is in progress, rather than showing an empty grid", async () => {
    stubFetch({ "/api/config": CONFIG, "/api/up-next": [], "/api/airing": [] });
    draw(<UpNext />);

    expect(await screen.findByText("Nothing in progress")).toBeTruthy();
  });

  it("lists what is coming, grouped by the day it airs", async () => {
    stubFetch({ "/api/config": CONFIG, "/api/up-next": [NEXT_UP], "/api/airing": AIRING });
    draw(<UpNext />);

    expect(await screen.findByText("Airing next")).toBeTruthy();
    // Two episodes a week apart are two headings, not one list of two rows.
    expect(screen.getAllByRole("heading", { level: 3 })).toHaveLength(2);
    expect(screen.getByText("S04E05")).toBeTruthy();
    expect(screen.getByText("Riches of Embarrassment")).toBeTruthy();
  });

  it("lists every episode of a season that lands at once", async () => {
    const sameDay: AiringItem[] = [1, 2, 3].map((n) => ({
      ...LASSO,
      episode_id: 950 + n,
      episode_number: n,
      episode_name: `Episode ${n}`,
      air_date: "2099-02-01",
    }));
    stubFetch({ "/api/config": CONFIG, "/api/up-next": [NEXT_UP], "/api/airing": sameDay });
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
    stubFetch({ "/api/config": CONFIG, "/api/up-next": [NEXT_UP], "/api/airing": [] });
    draw(<UpNext />);

    expect(await screen.findByText("Avatar: The Last Airbender")).toBeTruthy();
    expect(screen.queryByText("Airing next")).toBeNull();
  });

  it("keeps the shelf when only the calendar fails", async () => {
    // The page is for the shelf. A calendar that will not load is not worth
    // replacing it with an error.
    vi.stubGlobal("fetch", (input: string) => {
      const path = new URL(input, "http://localhost").pathname;
      if (path === "/api/airing") return Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) } as Response);
      const body = path === "/api/config" ? CONFIG : [NEXT_UP];
      return Promise.resolve({ ok: true, json: () => Promise.resolve(body) } as Response);
    });
    draw(<UpNext />);

    expect(await screen.findByText("Avatar: The Last Airbender")).toBeTruthy();
    expect(screen.queryByText("Airing next")).toBeNull();
  });

  it("shows the server's own words when the request fails", async () => {
    vi.stubGlobal("fetch", (input: string) =>
      new URL(input, "http://localhost").pathname === "/api/config"
        ? Promise.resolve({ ok: true, json: () => Promise.resolve(CONFIG) } as Response)
        : Promise.resolve({
            ok: false,
            status: 500,
            statusText: "Internal Server Error",
            json: () => Promise.resolve({ detail: "the library is locked" }),
          } as Response),
    );
    draw(<UpNext />);

    expect(await screen.findByRole("alert")).toHaveProperty("textContent", expect.stringContaining("locked"));
  });
});

describe("Library", () => {
  it("renders progress against the catalog count", async () => {
    stubFetch({ "/api/config": CONFIG, "/api/titles": [FRIENDS] });
    draw(<Library />);

    expect(await screen.findByText("Friends")).toBeTruthy();
    expect(screen.getByText("228 / 228")).toBeTruthy();
    expect(screen.getByRole("progressbar").getAttribute("aria-valuenow")).toBe("100");
  });

  it("shows a bare count, and no bar, for a title with no catalog count", async () => {
    // The denominator is what a bar needs. Without one, claiming 100% because
    // every known episode is watched would be a lie about an unenriched show.
    stubFetch({ "/api/config": CONFIG, "/api/titles": [UNENRICHED] });
    draw(<Library />);

    expect(await screen.findByText("3 watched")).toBeTruthy();
    expect(screen.queryByRole("progressbar")).toBeNull();
  });

  it("shows a full bar and the episodes TMDB does not list, together", async () => {
    // Friends: 228 of TMDB's 228, plus the eight finales TheTVDB splits in two.
    stubFetch({ "/api/config": CONFIG, "/api/titles": [{ ...FRIENDS, unmatched_watched: 8 }] });
    draw(<Library />);

    expect(await screen.findByText("228 / 228")).toBeTruthy();
    expect(screen.getByRole("progressbar").getAttribute("aria-valuenow")).toBe("100");
    // The card is a glance — how far through, nothing else. Where the export
    // and TMDB disagree is a footnote, and belongs on the title page.
    expect(screen.queryByText(/not in TMDB/i)).toBeNull();
  });

  it("draws no bar for a show whose numbering TMDB does not share", async () => {
    // Sidemen Sundays: 320 watched, none on TMDB's 461-episode list. A 0% bar
    // would be true and would read as "not started".
    stubFetch({
      "/api/config": CONFIG,
      "/api/titles": [{ ...FRIENDS, episodes_watched: 0, unmatched_watched: 320, total_episodes: 461 }],
    });
    draw(<Library />);

    expect(await screen.findByText("320 watched")).toBeTruthy();
    expect(screen.queryByRole("progressbar")).toBeNull();
  });

  it("falls back to initials when a title has no poster", async () => {
    stubFetch({ "/api/config": CONFIG, "/api/titles": [UNENRICHED] });
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
    expect(screen.getByText("At least")).toBeTruthy();
    expect(screen.getByText("2,509 hours")).toBeTruthy();
    expect(screen.getByText("74")).toBeTruthy();
  });
});

describe("Title", () => {
  const DETAIL = {
    ...FRIENDS,
    unmatched_watched: 1,
    overview: "Six friends.",
    backdrop_path: null,
    first_air_date: "1994-09-22",
    last_air_date: "2004-05-06",
    runtime: 22,
    tmdb_id: 1668,
    imdb_id: "tt0108778",
    episodes: [
      {
        id: 1,
        season_number: 1,
        episode_number: 1,
        name: "The One Where It Begins",
        overview: null,
        air_date: "1994-09-22",
        runtime: 22,
        still_path: null,
        watch_count: 2,
        last_watched_at: "2021-04-23 00:23:28",
      },
      {
        id: 2,
        season_number: 0,
        episode_number: 1,
        name: "The One With The Reunion",
        overview: null,
        air_date: "2004-05-06",
        runtime: 40,
        still_path: null,
        watch_count: 1,
        last_watched_at: "2021-04-23 00:23:28",
      },
    ],
    unmatched: [{ season_number: 6, episode_number: 25, watch_count: 1, last_watched_at: "2018-06-01 00:00:00" }],
  };

  function drawTitle(detail: unknown) {
    stubFetch({ "/api/config": CONFIG, "/api/titles/1": detail });
    return render(
      <MemoryRouter initialEntries={["/titles/1"]}>
        <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
          <Routes>
            <Route path="/titles/:id" element={<TitlePanel />} />
          </Routes>
        </QueryClientProvider>
      </MemoryRouter>,
    );
  }

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
    stubFetch({
      "/api/config": CONFIG,
      "/api/titles/1": {
        ...FRIENDS,
        episodes_watched: 0,
        unmatched_watched: 60,
        total_episodes: 461,
        overview: null,
        backdrop_path: null,
        first_air_date: null,
        last_air_date: null,
        runtime: null,
        tmdb_id: 1,
        imdb_id: null,
        episodes: [],
        unmatched: MANY,
      },
    });
    render(
      <MemoryRouter initialEntries={["/titles/1"]}>
        <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
          <Routes>
            <Route path="/titles/:id" element={<TitlePanel />} />
          </Routes>
        </QueryClientProvider>
      </MemoryRouter>,
    );

    // The headline is the count and the reason, not three hundred chips.
    expect(await screen.findByText(/none of them on TMDB/)).toBeTruthy();
    expect(screen.getByText("Show all 60")).toBeTruthy();
    // No bar: a 0% one beside 60 watched episodes reads as "not started".
    expect(screen.queryByRole("progressbar")).toBeNull();
  });
});
