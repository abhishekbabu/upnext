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
import type { Config, Stats, Timeline, TimelineItem, TitleDetail, TitleSummary, UpNextItem } from "@/lib/api";
import { Library } from "@/panels/Library";
import { Timeline as TimelinePanel } from "@/panels/Timeline";
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
  air_date: "2006-04-14",
};

const TODAY = "2099-01-01";

const LASSO: TimelineItem = {
  title_id: 7,
  name: "Ted Lasso",
  poster_path: "/lasso.jpg",
  episode_id: 901,
  season_number: 4,
  episode_number: 5,
  episode_name: "Riches of Embarrassment",
  air_date: TODAY,
};

/** Out yesterday, out today, and a week away: three days, two of them markable. */
const TIMELINE: Timeline = {
  today: TODAY,
  episodes: [
    { ...LASSO, episode_id: 900, episode_number: 4, episode_name: "Smoke and Mirrors", air_date: "2098-12-31" },
    LASSO,
    { ...LASSO, episode_id: 902, episode_number: 6, episode_name: null, air_date: "2099-01-08" },
  ],
};

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
  writes = [];
  vi.stubGlobal("fetch", (input: string, init?: RequestInit) => {
    const path = new URL(input, "http://localhost").pathname;
    if (init?.method && init.method !== "GET") {
      writes.push(`${init.method} ${path}`);
      return Promise.resolve({ ok: true, status: 204 } as Response);
    }
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
/** Every POST and DELETE the panel sent, as "METHOD /path". */
let writes: string[] = [];

/** An absent section proves nothing until the request behind it has settled. */
async function settled(key: string) {
  await waitFor(() => expect(client.getQueryState([key])?.status).toMatch(/^(success|error)$/));
}

afterEach(() => vi.unstubAllGlobals());

describe("UpNext", () => {
  it("shows the next episode of each show in progress", async () => {
    stubFetch({ "/api/up-next": [NEXT_UP] });
    draw(<UpNext />);

    expect(await screen.findByText("Avatar: The Last Airbender")).toBeTruthy();
    expect(screen.getByText("S02E02")).toBeTruthy();
    expect(screen.getByText("A Fight, Once Begun")).toBeTruthy();
    expect(screen.getByRole("link")).toHaveProperty("href", expect.stringContaining("/titles/1"));
  });

  it("says so when nothing is in progress, rather than showing an empty grid", async () => {
    stubFetch({ "/api/up-next": [] });
    draw(<UpNext />);

    expect(await screen.findByText("Nothing in progress")).toBeTruthy();
  });

  it("searches and sorts the shelf, keeping both in the address", async () => {
    const stick = { ...NEXT_UP, title_id: 2, episode_id: 45, name: "Stick", air_date: "2026-11-03" };
    stubFetch({ "/api/up-next": [NEXT_UP, stick] });
    draw(<UpNext />, "/up-next?sort=newest");

    await screen.findByText("Stick");
    expect(screen.getAllByRole("link").map((link) => link.textContent?.slice(0, 5))).toEqual(["Stick", "Avata"]);
    expect(screen.getByRole("combobox", { name: "Sort" })).toHaveProperty("value", "newest");

    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "avatar" } });
    await waitFor(() => expect(screen.queryByText("Stick")).toBeNull());
    expect(screen.getByText("Avatar: The Last Airbender")).toBeTruthy();
  });

  it("says when a search finds nothing on the shelf", async () => {
    stubFetch({ "/api/up-next": [NEXT_UP] });
    draw(<UpNext />, "/up-next?q=zzz");

    expect(await screen.findByText("Nothing matching “zzz”")).toBeTruthy();
  });

  it("marks the next episode from the shelf", async () => {
    stubFetch({ "/api/up-next": [NEXT_UP] });
    draw(<UpNext />);

    fireEvent.click(await screen.findByRole("button", { name: "Mark S02E02 watched" }));
    await waitFor(() => expect(writes).toEqual(["POST /api/episodes/44/watch"]));
  });

  it("shows the server's own words when the request fails", async () => {
    stubFetch({ "/api/up-next": new Fails({ detail: "the library is locked" }) });
    draw(<UpNext />);

    expect(await screen.findByRole("alert")).toHaveProperty("textContent", expect.stringContaining("locked"));
  });

  it("shows the status line, not a list, when validation fails", async () => {
    // FastAPI's 422 carries `detail` as a list of objects.
    stubFetch({ "/api/up-next": new Fails({ detail: [{ msg: "bad" }] }, 422) });
    draw(<UpNext />);

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("422 Unprocessable Entity");
    expect(alert.textContent).not.toContain("[object Object]");
  });
});

describe("Timeline", () => {
  it("lists unwatched episodes by the day they air", async () => {
    stubFetch({ "/api/timeline": TIMELINE });
    draw(<TimelinePanel />);

    expect(await screen.findByText("Yesterday")).toBeTruthy();
    expect(screen.getByText("Today")).toBeTruthy();
    expect(screen.getAllByRole("heading", { level: 2 })).toHaveLength(3);
    expect(screen.getByText("Riches of Embarrassment")).toBeTruthy();
  });

  it("offers to mark what is out, and only that", async () => {
    stubFetch({ "/api/timeline": TIMELINE });
    draw(<TimelinePanel />);

    await screen.findByText("Yesterday");
    expect(screen.getByRole("button", { name: "Mark S04E04 watched" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Mark S04E05 watched" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Mark S04E06 watched" })).toBeNull();
  });

  it("sends the mark, and refetches rather than following the link", async () => {
    stubFetch({ "/api/timeline": TIMELINE });
    draw(<TimelinePanel />);

    // The row is a link; `false` is the click's default prevented, so it was not followed.
    expect(fireEvent.click(await screen.findByRole("button", { name: "Mark S04E05 watched" }))).toBe(false);
    await waitFor(() => expect(writes).toEqual(["POST /api/episodes/901/watch"]));
  });

  it("lists every episode of a season that lands at once", async () => {
    const sameDay = {
      today: TODAY,
      episodes: [1, 2, 3].map((n) => ({ ...LASSO, episode_id: 950 + n, episode_number: n, air_date: TODAY })),
    };
    stubFetch({ "/api/timeline": sameDay });
    draw(<TimelinePanel />);

    // One day, three rows, each its own button.
    expect(await screen.findByText("S04E01")).toBeTruthy();
    expect(screen.getAllByRole("heading", { level: 2 })).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: /^Mark S04E0\d watched$/ })).toHaveLength(3);
  });

  it("says when there is nothing to mark or wait for", async () => {
    stubFetch({ "/api/timeline": { today: TODAY, episodes: [] } });
    draw(<TimelinePanel />);

    expect(await screen.findByText("All caught up")).toBeTruthy();
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

  it("sorts by name, and by progress with the unmeasured last", async () => {
    const half = { ...FRIENDS, id: 3, name: "Arrow", episodes_watched: 114 };
    stubFetch({ "/api/titles": [FRIENDS, UNENRICHED, half] });
    const { container } = draw(<Library />, "/library?sort=name");

    const names = () => [...container.querySelectorAll("li p[title]")].map((p) => p.textContent);
    await screen.findByText("Arrow");
    expect(names()).toEqual(["Armor Wars", "Arrow", "Friends"]);

    fireEvent.change(screen.getByRole("combobox", { name: "Sort" }), { target: { value: "progress" } });
    await waitFor(() => expect(names()).toEqual(["Friends", "Arrow", "Armor Wars"]));
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
    today: "2026-09-01",
    episodes: [
      {
        id: 1,
        season_number: 1,
        episode_number: 1,
        name: "The One Where It Begins",
        air_date: "1994-09-22",
        watch_count: 2,
        marked_here: false,
      },
      {
        id: 2,
        season_number: 0,
        episode_number: 1,
        name: "The One With The Reunion",
        air_date: "2004-05-06",
        watch_count: 1,
        marked_here: false,
      },
    ],
    unmatched: [{ season_number: 6, episode_number: 25, watch_count: 1, last_watched_at: "2018-06-01 00:00:00" }],
  };

  it("changes the status in place", async () => {
    drawTitle(DETAIL);

    const picker = await screen.findByRole("combobox", { name: "Status" });
    expect(picker).toHaveProperty("value", "completed");
    fireEvent.change(picker, { target: { value: "watch_later" } });
    await waitFor(() => expect(writes).toEqual(["PUT /api/titles/1/status"]));
  });

  it("offers to mark an aired, unwatched episode and to unmark one marked here", async () => {
    const episode = DETAIL.episodes[0]!;
    drawTitle({
      ...DETAIL,
      episodes: [
        { ...episode, id: 5, episode_number: 5, watch_count: 0 },
        { ...episode, id: 6, episode_number: 6, watch_count: 1, marked_here: true },
        { ...episode, id: 7, episode_number: 7, watch_count: 0, air_date: "2026-09-02" },
        { ...episode, id: 8, episode_number: 8, watch_count: 1 },
      ],
    });

    fireEvent.click(await screen.findByRole("button", { name: "Mark S01E05 watched" }));
    fireEvent.click(screen.getByRole("button", { name: "Unmark S01E06" }));
    await waitFor(() => expect(writes).toEqual(["POST /api/episodes/5/watch", "DELETE /api/episodes/6/watch"]));
    // Not out yet, and imported history: neither has a button.
    expect(screen.queryByRole("button", { name: /S01E07/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /S01E08/ })).toBeNull();
  });

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
      today: "2026-09-01",
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
