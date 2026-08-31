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
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Stats, TitleSummary, UpNextItem } from "@/lib/api";
import { Library } from "@/panels/Library";
import { Stats as StatsPanel } from "@/panels/Stats";
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
  last_watched_at: "2021-04-23 00:23:28",
};

const UNENRICHED: TitleSummary = {
  ...FRIENDS,
  id: 2,
  name: "Armor Wars",
  poster_path: null,
  total_episodes: null,
  status: "watchlist",
  episodes_watched: 3,
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
    stubFetch({ "/api/config": CONFIG, "/api/up-next": [NEXT_UP] });
    draw(<UpNext />);

    expect(await screen.findByText("Avatar: The Last Airbender")).toBeTruthy();
    expect(screen.getByText("S02E02")).toBeTruthy();
    expect(screen.getByText("A Fight, Once Begun")).toBeTruthy();
    expect(screen.getByRole("link")).toHaveProperty("href", expect.stringContaining("/titles/1"));
  });

  it("says so when nothing is in progress, rather than showing an empty grid", async () => {
    stubFetch({ "/api/config": CONFIG, "/api/up-next": [] });
    draw(<UpNext />);

    expect(await screen.findByText("Nothing in progress")).toBeTruthy();
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
