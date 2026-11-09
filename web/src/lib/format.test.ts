import { describe, expect, it } from "vitest";
import {
  airingDay,
  counted,
  episodeCode,
  hourName,
  hours,
  initials,
  monthName,
  poster,
  progressOf,
  shortDate,
  weekdays,
} from "@/lib/format";

const BASE = "https://image.tmdb.org/t/p";

describe("poster", () => {
  it("joins the CDN base, the size and the path", () => {
    expect(poster(BASE, "/abc.jpg")).toBe("https://image.tmdb.org/t/p/w342/abc.jpg");
    expect(poster(BASE, "/abc.jpg", "w154")).toBe("https://image.tmdb.org/t/p/w154/abc.jpg");
  });

  it("returns null rather than a broken URL when there is no artwork", () => {
    expect(poster(BASE, null)).toBeNull();
    expect(poster(BASE, "")).toBeNull();
  });
});

describe("episodeCode", () => {
  it("pads both numbers so a season list stays in columns", () => {
    expect(episodeCode(1, 4)).toBe("S01E04");
    expect(episodeCode(10, 22)).toBe("S10E22");
  });

  it("keeps season 0, which is specials rather than a missing season", () => {
    expect(episodeCode(0, 1)).toBe("S00E01");
  });
});

describe("progressOf", () => {
  const ENRICHED = "2026-08-31T00:00:00+00:00";
  const title = (watched: number, unmatched: number, total: number | null, enriched_at: string | null = ENRICHED) => ({
    episodes_watched: watched,
    unmatched_watched: unmatched,
    total_episodes: total,
    enriched_at,
  });

  it("measures the watched share of TMDB's list", () => {
    expect(progressOf(title(114, 0, 228))).toEqual({
      kind: "measured",
      watched: 114,
      total: 228,
      share: 0.5,
    });
  });

  it("measures against the list alone, never adding the unmatched", () => {
    // Friends: a complete watch of TMDB's 228, plus the eight season finales
    // TheTVDB splits in two and TMDB counts once.
    expect(progressOf(title(228, 8, 228))).toEqual({
      kind: "measured",
      watched: 228,
      total: 228,
      share: 1,
    });
  });

  it("tells a title TMDB has not been asked about apart from one it disagrees with", () => {
    // Unenriched: everything is unmatched only because there is nothing to
    // match against. Reporting that as a disagreement would be a lie.
    expect(progressOf(title(0, 12, null, null))).toEqual({ kind: "unenriched", watched: 12 });
  });

  it("never adds matched and unmatched together when TMDB gives no total", () => {
    // Enriched, but TMDB has no episode count: the matched figure is the one
    // that means something, and the rest are on the title page.
    expect(progressOf(title(5, 3, null))).toEqual({ kind: "counted", watched: 5 });
  });

  it("draws no bar when TMDB has a list and nothing is on it", () => {
    // Sidemen Sundays: numbered by year in the export, 1..N at TMDB. A 0% bar
    // beside 320 watched episodes is true and reads as "not started".
    expect(progressOf(title(0, 320, 461))).toEqual({ kind: "unmatched", unmatched: 320, total: 461 });
  });

  it("has nothing to say about a title nobody has watched", () => {
    expect(progressOf(title(0, 0, null, null))).toEqual({ kind: "none" });
    expect(progressOf(title(0, 0, null))).toEqual({ kind: "none" });
  });

  it("clamps when TMDB revises a count below what was matched against it", () => {
    const result = progressOf(title(240, 0, 228));
    expect(result.kind === "measured" && result.share).toBe(1);
  });
});

describe("shortDate", () => {
  it("reads a watch timestamp as the day it happened", () => {
    expect(shortDate("2018-05-12 01:10:14", "en-GB")).toBe("12 May 2018");
  });

  it("does not shift a date across a timezone boundary", () => {
    // Parsed as UTC and rendered as UTC. Left to the local timezone, an early
    // morning watch lands on the previous day west of Greenwich.
    expect(shortDate("2021-01-01 00:30:00", "en-GB")).toBe("1 Jan 2021");
  });

  it("follows the reader's locale for ordering", () => {
    // The parameter exists so this file can assert anything at all: the default
    // follows the browser, which differs between a developer and CI.
    expect(shortDate("2018-05-12", "en-US")).toBe("May 12, 2018");
  });

  it("is empty for nothing, rather than 'Invalid Date'", () => {
    expect(shortDate(null)).toBe("");
    expect(shortDate("")).toBe("");
    expect(shortDate("not a date")).toBe("");
  });
});

describe("hours", () => {
  it("groups thousands", () => {
    expect(hours(150_540, "en-US")).toBe("2,509 hours");
  });

  it("says nothing below an hour", () => {
    expect(hours(45)).toBe("");
  });

  it("is singular at exactly one", () => {
    expect(hours(60)).toBe("1 hour");
  });
});

describe("airingDay", () => {
  const TODAY = "2026-09-01";

  it("names today and tomorrow rather than dating them", () => {
    expect(airingDay(TODAY, TODAY)).toBe("Today");
    expect(airingDay("2026-09-02", TODAY)).toBe("Tomorrow");
    expect(airingDay("2026-08-31", TODAY)).toBe("Yesterday");
  });

  it("gives a weekday and a date for anything further out", () => {
    // Asserted by part rather than as one string: how a locale punctuates a
    // date, and whether September abbreviates to "Sep" or "Sept", is ICU's
    // business and changes between runtimes. What must hold is that all three
    // parts are there.
    const label = airingDay("2026-09-08", TODAY, "en-GB");
    expect(label).toContain("Tue");
    expect(label).toContain("8");
    expect(label).toContain("Sep");
  });

  it("adds the year only once the calendar leaves this one", () => {
    // A list running a few weeks out does not need it; one reaching January
    // does, or the first of January is four months ambiguous.
    expect(airingDay("2026-12-25", TODAY, "en-GB")).not.toContain("2026");
    expect(airingDay("2027-01-01", TODAY, "en-GB")).toContain("2027");
  });

  it("crosses a month end without arithmetic of its own", () => {
    expect(airingDay("2026-10-01", "2026-09-30")).toBe("Tomorrow");
  });

  it("says nothing about a date it cannot parse", () => {
    expect(airingDay("", TODAY)).toBe("");
    expect(airingDay("not-a-date", TODAY)).toBe("");
  });
});

describe("initials", () => {
  it("takes the first letter of the first two meaningful words", () => {
    expect(initials("Armor Wars")).toBe("AW");
    expect(initials("Avatar: The Last Airbender")).toBe("AL");
  });

  it("keeps a possessive as one word", () => {
    // Splitting on the apostrophe leaves a stray "s" that becomes an initial:
    // "Aegon's Conquest" read as AS rather than AC.
    expect(initials("Aegon's Conquest")).toBe("AC");
    expect(initials("Kuroko's Basketball")).toBe("KB");
    expect(initials("Aegon’s Conquest")).toBe("AC");
  });

  it("drops leading articles, which would collide across half a shelf", () => {
    expect(initials("The Office")).toBe("O");
    expect(initials("The Last of Us")).toBe("LU");
  });

  it("always returns something, even for a name that is all punctuation", () => {
    expect(initials("?")).toBe("?");
    expect(initials("24")).toBe("2");
  });
});

describe("counted", () => {
  it("agrees the noun with the count", () => {
    expect(counted(1, "day", "en-US")).toBe("1 day");
    expect(counted(1200, "episode", "en-US")).toBe("1,200 episodes");
    expect(counted(0, "episode", "en-US")).toBe("0 episodes");
  });
});

describe("monthName", () => {
  it("names a month label in the reader's locale", () => {
    expect(monthName("2021-03", "en-US")).toBe("Mar 2021");
    expect(monthName("2021-12", "en-GB")).toBe("Dec 2021");
  });

  it("leaves a label it cannot read as it is", () => {
    expect(monthName("someday")).toBe("someday");
  });
});

describe("weekdays", () => {
  it("starts on Monday, as the API counts", () => {
    expect(weekdays("en-US")).toEqual(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]);
    expect(weekdays("en-US", "long")[6]).toBe("Sunday");
  });
});

describe("hourName", () => {
  it("names an hour the way the locale does", () => {
    expect(hourName(22, "en-US")).toBe("10 PM");
    expect(hourName(0, "en-US")).toBe("12 AM");
    expect(hourName(22, "en-GB")).toBe("22");
  });
});
