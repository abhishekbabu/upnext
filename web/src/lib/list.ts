/**
 * Searching and sorting a list of titles, shared by the shelves that have one.
 *
 * The state lives in the address — `?q=` and `?sort=` beside any filter of the
 * page's own — so a narrowed list can be linked, survives a reload, and is
 * still there after following a title and coming back.
 */

import { useSearchParams } from "react-router-dom";

/**
 * One way to order a list. `compare` is null for the server's own order,
 * which is what the first option always is: the server already sends a list
 * most recently watched first.
 */
export type SortOption<T, K extends string = string> = {
  value: K;
  label: string;
  compare: ((a: T, b: T) => number) | null;
};

/** The list's search, sort and other parameters, and a setter that keeps the rest. */
export function useListParams<T, K extends string>(sorts: readonly SortOption<T, K>[]) {
  const [params, setParams] = useSearchParams();
  const sort = sorts.find((option) => option.value === params.get("sort")) ?? sorts[0]!;

  /** One parameter changed, the others kept; replaced, so typing is not history. */
  const set = (key: string, value: string | null) =>
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        if (value) next.set(key, value);
        else next.delete(key);
        return next;
      },
      { replace: true },
    );

  return { params, search: params.get("q") ?? "", sort, set };
}

/** The items whose name contains `search`, in the order `sort` asks for. */
export function narrow<T extends { name: string }>(items: T[], search: string, sort: SortOption<T>): T[] {
  const needle = search.trim().toLowerCase();
  const found = needle ? items.filter((item) => item.name.toLowerCase().includes(needle)) : items;
  return sort.compare ? [...found].sort(sort.compare) : found;
}

/** A to Z, ignoring case and accents. */
export function byName(a: { name: string }, b: { name: string }): number {
  return a.name.localeCompare(b.name, undefined, { sensitivity: "base" });
}

/** Highest first, with nulls — nothing known — last rather than counted as zero. */
export function descending<T>(key: (item: T) => number | string | null) {
  return (a: T, b: T): number => {
    const x = key(a);
    const y = key(b);
    if (x === y) return 0;
    if (x === null) return 1;
    if (y === null) return -1;
    return x < y ? 1 : -1;
  };
}
