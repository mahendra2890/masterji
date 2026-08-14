import { describe, expect, it } from "vitest";
import { place } from "./cohort";

describe("place", () => {
  it("writes the ordinary places", () => {
    expect(place(1)).toBe("1st");
    expect(place(2)).toBe("2nd");
    expect(place(3)).toBe("3rd");
    expect(place(4)).toBe("4th");
    expect(place(21)).toBe("21st");
    expect(place(22)).toBe("22nd");
    expect(place(23)).toBe("23rd");
  });

  it("writes the teens the way English does", () => {
    // The reason this function exists rather than being three lines inline.
    // A cohort of forty reaches all three of these on its first load.
    expect(place(11)).toBe("11th");
    expect(place(12)).toBe("12th");
    expect(place(13)).toBe("13th");
  });

  it("keeps the teens exception past a hundred", () => {
    expect(place(111)).toBe("111th");
    expect(place(112)).toBe("112th");
    expect(place(113)).toBe("113th");
    expect(place(121)).toBe("121st");
  });

  it("covers every place a forty-member board can produce", () => {
    // Every rank 1..40 renders as itself plus two letters. A cohort is the
    // size this is for, so nothing in that range may come back "undefined".
    for (let rank = 1; rank <= 40; rank += 1) {
      expect(place(rank)).toMatch(new RegExp(`^${rank}(st|nd|rd|th)$`));
    }
  });
});
