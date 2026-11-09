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
 * What can honestly be said about how far through a title someone is.
 *
 * One number cannot carry it. TMDB's episode list is the source of truth for
 * what a show *is*; the import is the source of truth for what was *watched*,
 * and the two do not always divide a show the same way. A viewing TMDB's list
 * has no episode for is still a viewing — it just cannot be a percentage.
 *
 * So this returns which of five things is true, and the panels render each.
 */
export type Progress =
  /** Nothing watched, nothing to measure. */
  | { kind: "none" }
  /**
   * TMDB has not been asked yet, so every viewing is unmatched for want of a
   * list. The opposite statement to `unmatched`, and never drawn like it.
   */
  | { kind: "unenriched"; watched: number }
  /** Watched, with no catalog total to measure against. */
  | { kind: "counted"; watched: number }
  /** Matched to TMDB's list, so a bar means what it looks like. */
  | { kind: "measured"; watched: number; total: number; share: number }
  /**
   * TMDB has answered and not one viewing is on its list. A 0% bar beside 320
   * watched episodes would be true and would read as "not started", so there
   * is none: the counts say it better.
   */
  | { kind: "unmatched"; unmatched: number; total: number | null };

export function progressOf(
  title: Pick<TitleSummary, "episodes_watched" | "unmatched_watched" | "total_episodes" | "enriched_at">,
): Progress {
  const { episodes_watched: watched, unmatched_watched: unmatched, total_episodes: total } = title;

  if (!title.enriched_at) return unmatched > 0 ? { kind: "unenriched", watched: unmatched } : { kind: "none" };
  // From here the two counts are different statements and are never added.
  if (watched === 0 && unmatched > 0) return { kind: "unmatched", unmatched, total };
  if (!total) return watched > 0 ? { kind: "counted", watched } : { kind: "none" };

  // Clamped: TMDB revises episode counts downward as contributors edit, and a
  // list that shrinks below what was matched against it should read as done.
  return { kind: "measured", watched, total, share: Math.min(watched / total, 1) };
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
  // Only the date half is ever shown.
  const date = utcDate(value);
  if (!date) return "";
  return date.toLocaleDateString(locale, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}

/**
 * The heading one day of the timeline sits under: "Yesterday", "Today",
 * "Tomorrow", or "Mon, 7 Sep".
 *
 * `today` is a parameter rather than `new Date()` for the same reason `locale`
 * is: a function that reads the clock cannot be asserted against, and this one
 * draws the boundary the whole list depends on. Both are "YYYY-MM-DD", which
 * compares as text, so nothing here builds a Date to decide the label — only
 * to name the weekday.
 *
 * The year appears only when it is not the current one. A calendar of the next
 * few weeks does not need it; one reaching into January does.
 */
export function airingDay(airDate: string, today: string, locale?: string): string {
  if (airDate === today) return "Today";

  const date = utcDate(airDate);
  if (!date) return "";

  const todayDate = utcDate(today);
  if (todayDate && date.getTime() - todayDate.getTime() === DAY_MS) return "Tomorrow";
  if (todayDate && todayDate.getTime() - date.getTime() === DAY_MS) return "Yesterday";

  return date.toLocaleDateString(locale, {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: todayDate && date.getUTCFullYear() !== todayDate.getUTCFullYear() ? "numeric" : undefined,
    timeZone: "UTC",
  });
}

const DAY_MS = 24 * 60 * 60 * 1000;

/**
 * The date half of a timestamp or an air date, as a UTC Date.
 *
 * Parsing only the date half is what keeps a timezone from shifting a watch
 * onto the previous day, and returning null rather than an Invalid Date makes
 * every caller handle the miss.
 */
function utcDate(value: string): Date | null {
  const [datePart] = value.split(/[ T]/);
  if (!datePart) return null;
  const [year, month, day] = datePart.split("-").map(Number);
  if (!year || !month || !day) return null;
  const date = new Date(Date.UTC(year, month - 1, day));
  return Number.isNaN(date.getTime()) ? null : date;
}

/** "4,240", grouped however the reader's locale groups digits. */
export function count(n: number, locale?: string): string {
  return n.toLocaleString(locale);
}

/** "2,509 hours", or "" below an hour — a floor is not worth a rounding argument. */
export function hours(minutes: number, locale?: string): string {
  const total = Math.floor(minutes / 60);
  if (total < 1) return "";
  return `${count(total, locale)} ${total === 1 ? "hour" : "hours"}`;
}

/** "11 episodes", "1 day": a count with its noun, agreeing. */
export function counted(n: number, noun: string, locale?: string): string {
  return `${count(n, locale)} ${n === 1 ? noun : `${noun}s`}`;
}

/** "Mar 2021" from a "2021-03" month label. */
export function monthName(label: string, locale?: string): string {
  const [year, month] = label.split("-").map(Number);
  if (!year || !month) return label;
  return new Date(Date.UTC(year, month - 1, 1)).toLocaleDateString(locale, {
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

/** The days of the week, Monday first — the order the API counts them in. */
export function weekdays(locale?: string, style: "short" | "long" = "short"): string[] {
  // 1 January 2024 was a Monday.
  return Array.from({ length: 7 }, (_, day) =>
    new Date(Date.UTC(2024, 0, 1 + day)).toLocaleDateString(locale, { weekday: style, timeZone: "UTC" }),
  );
}

/** "6 PM" or "18", however the reader's locale names an hour. */
export function hourName(hour: number, locale?: string): string {
  return new Date(Date.UTC(2024, 0, 1, hour)).toLocaleTimeString(locale, { hour: "numeric", timeZone: "UTC" });
}

/** Up to two initials from a title: "The Last of Us" -> "LU". */
export function initials(name: string): string {
  const words = name
    // Apostrophes come out before anything else splits on punctuation, so a
    // possessive stays one word: "Aegon's Conquest" is AC, not AS.
    .replace(/['\u2018\u2019]/g, "")
    .replace(/[^\p{L}\p{N} ]/gu, " ")
    .split(" ")
    .filter((word) => word && !STOP_WORDS.has(word.toLowerCase()));
  if (words.length === 0) return name.slice(0, 1).toUpperCase() || "?";
  return words
    .slice(0, 2)
    .map((word) => word[0]!.toUpperCase())
    .join("");
}

// Dropped so "The Office" reads as "O" rather than "TO", which would collide
// with half a shelf.
const STOP_WORDS = new Set(["the", "a", "an", "of", "and"]);
