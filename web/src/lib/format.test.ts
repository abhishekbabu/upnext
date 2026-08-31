import { describe, expect, it } from "vitest";
import { episodeCode, hours, poster, progress, shortDate, titleWithYear } from "@/lib/format";

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

describe("progress", () => {
  it("is the watched share of the catalog's episode count", () => {
    expect(progress({ episodes_watched: 118, total_episodes: 236 })).toBe(0.5);
  });

  it("is null without a catalog count, rather than a full bar", () => {
    // An unenriched title has watches but no denominator. Treating the watched
    // count as the total would claim every unenriched show is finished.
    expect(progress({ episodes_watched: 12, total_episodes: null })).toBeNull();
    expect(progress({ episodes_watched: 12, total_episodes: 0 })).toBeNull();
  });

  it("clamps rather than overflowing when TMDB revises a count downward", () => {
    expect(progress({ episodes_watched: 240, total_episodes: 228 })).toBe(1);
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
    expect(hours(150_540)).toBe("2,509 hours");
  });

  it("says nothing below an hour", () => {
    expect(hours(45)).toBe("");
  });

  it("is singular at exactly one", () => {
    expect(hours(60)).toBe("1 hour");
  });
});

describe("titleWithYear", () => {
  it("appends the year when there is one", () => {
    expect(titleWithYear("The Flash", 2014)).toBe("The Flash (2014)");
    expect(titleWithYear("Friends", null)).toBe("Friends");
  });
});
