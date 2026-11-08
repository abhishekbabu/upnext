import { describe, expect, it } from "vitest";
import { byName, descending, narrow, type SortOption } from "@/lib/list";

type Item = { name: string; year: number | null };
const items: Item[] = [
  { name: "the Office", year: 2005 },
  { name: "Arrow", year: null },
  { name: "Élite", year: 2018 },
];
const asSent: SortOption<Item> = { value: "recent", label: "Recently watched", compare: null };

describe("narrow", () => {
  it("keeps the server's order when the sort has no comparator", () => {
    expect(narrow(items, "", asSent)).toBe(items);
  });

  it("matches anywhere in the name, ignoring case and surrounding space", () => {
    expect(narrow(items, "  OFF ", asSent).map((item) => item.name)).toEqual(["the Office"]);
  });

  it("sorts a copy, leaving the list it was given alone", () => {
    const sorted = narrow(items, "", { value: "name", label: "Name", compare: byName });
    expect(sorted.map((item) => item.name)).toEqual(["Arrow", "Élite", "the Office"]);
    expect(items[0]!.name).toBe("the Office");
  });
});

describe("descending", () => {
  it("puts the highest first and what is unknown last", () => {
    const newest = [...items].sort(descending((item: Item) => item.year));
    expect(newest.map((item) => item.year)).toEqual([2018, 2005, null]);
  });
});
