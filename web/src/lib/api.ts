/**
 * The API client.
 *
 * Types here mirror the wire models in `adapters/inbound/web/api.py`. They are
 * the contract in both directions: a field added there and not here is dead
 * weight, and a field read here that the server stopped sending is a typecheck
 * failure rather than an `undefined` halfway down a render.
 */

export type Kind = "show" | "movie";
export type Status = "watching" | "completed" | "watchlist" | "stopped";

/** Every status, in the order a library is read: what you are on, then the rest. */
export const STATUSES: Status[] = ["watching", "watchlist", "completed", "stopped"];

export const STATUS_LABELS: Record<Status, string> = {
  watching: "Watching",
  watchlist: "Watchlist",
  completed: "Completed",
  stopped: "Stopped",
};

/** What the client needs to know about this installation to render at all. */
export type Config = {
  /** TMDB's artwork CDN. Joined to a poster_path with the size we want. */
  image_base: string;
};

export type TitleSummary = {
  id: number;
  kind: Kind;
  name: string;
  year: number | null;
  poster_path: string | null;
  air_status: string | null;
  /** What the catalog says the whole run is. Null for anything unenriched. */
  total_episodes: number | null;
  status: Status | null;
  is_favorite: boolean;
  /** Out of 10. upnext keeps a 10-point scale; TV Time rated out of 5. */
  rating: number | null;
  /**
   * Distinct episodes watched that TMDB's list contains, specials excluded.
   * The figure `total_episodes` is comparable to.
   */
  episodes_watched: number;
  /**
   * Distinct episodes watched that TMDB's list does not contain, counted by
   * what the export called them. Real viewings of something TMDB numbers
   * differently — TheTVDB splits eight double-length Friends episodes TMDB
   * counts once, and TV Time numbers Sidemen Sundays by year against TMDB's
   * 1..N, where not one of 320 viewings matches.
   */
  unmatched_watched: number;
  /** Null until TMDB has answered, which separates "not listed" from "not asked". */
  enriched_at: string | null;
  last_watched_at: string | null;
};

/** Viewings of an episode TMDB's list does not contain, in the export's numbering. */
export type UnmatchedViewing = {
  season_number: number;
  episode_number: number;
  watch_count: number;
  last_watched_at: string | null;
};

export type EpisodeRow = {
  id: number;
  season_number: number;
  episode_number: number;
  name: string | null;
  overview: string | null;
  air_date: string | null;
  runtime: number | null;
  still_path: string | null;
  /** Watches, so a rewatch shows as 2 rather than collapsing into "seen". */
  watch_count: number;
  last_watched_at: string | null;
};

export type TitleDetail = TitleSummary & {
  overview: string | null;
  backdrop_path: string | null;
  first_air_date: string | null;
  last_air_date: string | null;
  runtime: number | null;
  tmdb_id: number | null;
  imdb_id: string | null;
  episodes: EpisodeRow[];
  unmatched: UnmatchedViewing[];
};

export type UpNextItem = {
  title_id: number;
  name: string;
  kind: Kind;
  year: number | null;
  poster_path: string | null;
  episode_id: number;
  season_number: number;
  episode_number: number;
  episode_name: string | null;
  air_date: string | null;
  still_path: string | null;
  last_watched_at: string | null;
};

export type Stats = {
  watches: number;
  episodes_watched: number;
  titles_watched: number;
  first_watch: string | null;
  last_watch: string | null;
  /** A floor, not a total: only enriched episodes carry a runtime. */
  known_minutes: number;
  by_status: Record<string, number>;
};

/**
 * A failure the server described in its own words, ready to show as-is.
 *
 * Carries the status so a 404 can read as "no such title" rather than as a
 * fault, without matching on the wording.
 */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number = 0,
  ) {
    super(message);
  }
}

async function request<T>(path: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, { headers: { accept: "application/json" } });
  } catch {
    // fetch rejects only when the request never completed — the server is not
    // running, or the network is gone. Neither has a `detail` to show.
    throw new ApiError("Cannot reach the upnext server. Is `just serve` running?");
  }
  if (!response.ok) {
    // FastAPI writes `detail` for every failure it raises deliberately;
    // anything without one is a genuine fault and gets the status line.
    const body = await response.json().catch(() => null);
    throw new ApiError(body?.detail ?? `${response.status} ${response.statusText}`, response.status);
  }
  return response.json() as Promise<T>;
}

export const api = {
  config: () => request<Config>("/api/config"),
  titles: (status?: Status) =>
    request<TitleSummary[]>(status ? `/api/titles?status=${encodeURIComponent(status)}` : "/api/titles"),
  title: (id: number) => request<TitleDetail>(`/api/titles/${id}`),
  upNext: (limit = 24) => request<UpNextItem[]>(`/api/up-next?limit=${limit}`),
  stats: () => request<Stats>("/api/stats"),
};
