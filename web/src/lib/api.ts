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
export type Timeline = Schemas["Timeline"];
export type TimelineItem = Schemas["TimelineItem"];
export type Stats = Schemas["Stats"];

/** Every status, labelled, in the order a library is read: what you are on, then the rest. */
export const STATUS_LABELS: Record<Status, string> = {
  watching: "Watching",
  watch_later: "Watch later",
  watchlist: "Watchlist",
  completed: "Completed",
  stopped: "Stopped",
};

export const STATUSES = Object.keys(STATUS_LABELS) as Status[];

async function request<T>(path: string, method: "GET" | "POST" | "PUT" | "DELETE" = "GET", body?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      method,
      headers: { accept: "application/json", ...(body === undefined ? {} : { "content-type": "application/json" }) },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    // fetch rejects only when the request never completed — the server is not
    // running, or the network is gone. Neither has a `detail` to show.
    throw new Error("Cannot reach the upnext server. Is `just serve` running?");
  }
  if (!response.ok) {
    // FastAPI writes a string `detail` for every failure it raises deliberately;
    // a validation failure's is a list, and that and anything without one get
    // the status line.
    const body = await response.json().catch(() => null);
    const detail = body?.detail;
    throw new Error(typeof detail === "string" ? detail : `${response.status} ${response.statusText}`);
  }
  // A write answers 204, with no body to parse.
  return (response.status === 204 ? undefined : response.json()) as Promise<T>;
}

export const api = {
  config: () => request<Config>("/api/config"),
  titles: (status?: Status) =>
    request<TitleSummary[]>(status ? `/api/titles?status=${encodeURIComponent(status)}` : "/api/titles"),
  title: (id: number) => request<TitleDetail>(`/api/titles/${id}`),
  upNext: () => request<UpNextItem[]>("/api/up-next"),
  timeline: () => request<Timeline>("/api/timeline"),
  markWatched: (episodeId: number) => request<void>(`/api/episodes/${episodeId}/watch`, "POST"),
  unmarkWatched: (episodeId: number) => request<void>(`/api/episodes/${episodeId}/watch`, "DELETE"),
  setStatus: ({ titleId, status }: { titleId: number; status: Status }) =>
    request<void>(`/api/titles/${titleId}/status`, "PUT", { status }),
  stats: () => request<Stats>("/api/stats"),
};
