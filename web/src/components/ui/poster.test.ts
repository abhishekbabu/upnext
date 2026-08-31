import { describe, expect, it } from "vitest";
import { initials } from "@/components/ui/poster";

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
