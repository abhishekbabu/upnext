/**
 * Every query the app makes, in one place.
 *
 * Keys live here rather than at each call site so that two panels asking for
 * the same thing share one fetch and one cache entry.
 */

import { QueryClient, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Status } from "@/lib/api";

/** The cache policy the app runs under, and the one its tests render with. */
export function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // The library is a local SQLite file that only changes when the user
        // runs a command, so refetching because a window regained focus buys
        // nothing.
        refetchOnWindowFocus: false,
        staleTime: 60_000,
        // A failure here is the server's answer, not a blip; it is shown at once.
        retry: false,
      },
    },
  });
}

export function useConfig() {
  return useQuery({
    queryKey: ["config"],
    queryFn: api.config,
    // The artwork CDN does not move while the page is open, and every poster
    // waits on this — so it is fetched once and never revalidated.
    staleTime: Infinity,
  });
}

export function useTitles(status?: Status) {
  return useQuery({ queryKey: ["titles", status ?? "all"], queryFn: () => api.titles(status) });
}

export function useTitle(id: number) {
  return useQuery({ queryKey: ["title", id], queryFn: () => api.title(id) });
}

export function useUpNext() {
  return useQuery({ queryKey: ["up-next"], queryFn: api.upNext });
}

export function useTimeline() {
  return useQuery({ queryKey: ["timeline"], queryFn: api.timeline });
}

/**
 * Mark an episode watched, or take back the last time it was marked here.
 *
 * A viewing changes nearly every figure — the timeline, up next, the title's
 * progress, the library, stats — so everything but the config is refetched
 * rather than each cache entry being patched by hand.
 */
export function useWatch() {
  const client = useQueryClient();
  const refresh = () => client.invalidateQueries({ predicate: (query) => query.queryKey[0] !== "config" });
  const mark = useMutation({ mutationFn: api.markWatched, onSuccess: refresh });
  const unmark = useMutation({ mutationFn: api.unmarkWatched, onSuccess: refresh });
  return { mark, unmark };
}

export function useStats() {
  return useQuery({ queryKey: ["stats"], queryFn: api.stats });
}
