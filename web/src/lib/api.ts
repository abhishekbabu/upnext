/**
 * The API client.
 *
 * The types are generated: `adapters/inbound/web/api.py` is the contract,
 * `just api-types` writes it to `openapi.json` and from there to `schema.d.ts`,
 * and a test fails if either is stale. A field the server stops sending is a
 * typecheck failure in the panel that reads it.
 */

import type { components } from "@/lib/schema";

type Schemas = components["schemas"];

export type Status = Schemas["Status"];
export type Config = Schemas["Config"];
export type TitleSummary = Schemas["TitleSummary"];
export type TitleDetail = Schemas["TitleDetail"];
export type TitleEpisode = Schemas["TitleEpisode"];
export type UnmatchedViewing = Schemas["UnmatchedViewing"];
export type UpNextItem = Schemas["UpNextItem"];
export type Airing = Schemas["Airing"];
export type AiringItem = Schemas["AiringItem"];
export type Stats = Schemas["Stats"];

/** Every status, labelled, in the order a library is read: what you are on, then the rest. */
export const STATUS_LABELS: Record<Status, string> = {
  watching: "Watching",
  watchlist: "Watchlist",
  completed: "Completed",
  stopped: "Stopped",
};

export const STATUSES = Object.keys(STATUS_LABELS) as Status[];

/** A failure the server described in its own words, ready to show as-is. */
export class ApiError extends Error {}

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
    throw new ApiError(body?.detail ?? `${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  config: () => request<Config>("/api/config"),
  titles: (status?: Status) =>
    request<TitleSummary[]>(status ? `/api/titles?status=${encodeURIComponent(status)}` : "/api/titles"),
  title: (id: number) => request<TitleDetail>(`/api/titles/${id}`),
  upNext: () => request<UpNextItem[]>("/api/up-next"),
  airing: () => request<Airing>("/api/airing"),
  stats: () => request<Stats>("/api/stats"),
};
