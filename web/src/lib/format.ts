/**
 * How the library reads on screen.
 *
 * Every function here is pure and tested. Formatting drifts when each panel
 * does its own — one showing "S1E4" and another "1x04" is the kind of thing
 * nobody notices in review and everybody notices in use.
 */

import type { TitleSummary } from "@/lib/api";

/**
 * Poster widths TMDB actually serves. Asking for a size it does not have
 * returns a 404 image, so these are the only values `poster` accepts.
 */
export type PosterSize = "w154" | "w185" | "w342" | "w500" | "original";

/**
 * A TMDB artwork URL, or null when there is no artwork.
 *
 * Null rather than a placeholder path: whether a missing poster becomes an
 * initial, a blank tile or nothing at all is the caller's decision, and
 * returning a broken URL would take that away.
 */
export function poster(base: string, path: string | null, size: PosterSize = "w342"): string | null {
  if (!path) return null;
  return `${base}/${size}${path}`;
}

/** "S01E04" — padded, so a season list stays in columns. */
export function episodeCode(season: number, episode: number): string {
  return `S${String(season).padStart(2, "0")}E${String(episode).padStart(2, "0")}`;
}

/**
 * How far through a title someone is, 0 to 1, or null when it cannot be known.
 *
 * Null for an unenriched title: without a catalog episode count there is no
 * denominator, and showing a full bar because 12 of 12 known episodes are
 * watched would claim a show is finished when the library simply has not met
 * TMDB yet. A count above the total clamps rather than overflowing — rewatches
 * are counted distinctly, but TMDB revises episode counts downward too.
 */
export function progress(title: Pick<TitleSummary, "episodes_watched" | "total_episodes">): number | null {
  const { episodes_watched: watched, total_episodes: total } = title;
  if (!total || total <= 0) return null;
  return Math.min(watched / total, 1);
}

/**
 * "12 Feb 2018", ordered however the reader's locale orders a date.
 *
 * The locale is a parameter rather than a constant so that tests can pin one:
 * the default follows the browser, and asserting against it would pass in
 * London and fail in New York.
 */
export function shortDate(value: string | null, locale?: string): string {
  if (!value) return "";
  // Timestamps arrive as "2018-05-12 01:10:14" and air dates as "2018-05-12".
  // Only the date half is ever shown, and parsing just that avoids a timezone
  // shifting a watch onto the previous day.
  const [datePart] = value.split(/[ T]/);
  if (!datePart) return "";
  const [year, month, day] = datePart.split("-").map(Number);
  if (!year || !month || !day) return "";
  const date = new Date(Date.UTC(year, month - 1, day));
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString(locale, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}

/** "2,509 hours", or "" below an hour — a floor is not worth a rounding argument. */
export function hours(minutes: number): string {
  const total = Math.floor(minutes / 60);
  if (total < 1) return "";
  return `${total.toLocaleString()} ${total === 1 ? "hour" : "hours"}`;
}

/** The name with its year, the way a library lists it: "The Flash (2014)". */
export function titleWithYear(name: string, year: number | null): string {
  return year ? `${name} (${year})` : name;
}
