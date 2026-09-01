/**
 * Every query the app makes, in one place.
 *
 * Keys live here rather than at each call site so that two panels asking for
 * the same thing share one fetch and one cache entry.
 */

import { useQuery } from "@tanstack/react-query";
import { api, type Status } from "@/lib/api";

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

export function useUpNext(limit = 24) {
  return useQuery({ queryKey: ["up-next", limit], queryFn: () => api.upNext(limit) });
}

export function useAiring(limit = 24) {
  return useQuery({ queryKey: ["airing", limit], queryFn: () => api.airing(limit) });
}

export function useStats() {
  return useQuery({ queryKey: ["stats"], queryFn: api.stats });
}
