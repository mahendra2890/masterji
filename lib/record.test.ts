import { describe, expect, it } from "vitest";
import {
  anyRepeat,
  cycleOrdinals,
  newestFirst,
  ordinalLabel,
  recordSlice,
  rowsExtent,
} from "./record";

/** What these protect: two rows of one day used to be indistinguishable in the
 * record, and the phase drill-in's heading could state a range its own list
 * fell outside. Both answers are now computed from the rows, so both are
 * pinned here — the rendering that carries them is driven in a browser. */
describe("cycleOrdinals", () => {
  it("numbers the cycles of a day by id, not by payload order", () => {
    // The queryset orders by `-date` alone, so rows within a date arrive in
    // whatever order the database gives. Here the day's second cycle (id 8)
    // arrives first, and must still read as the second.
    const ordinals = cycleOrdinals([
      { id: 8, date: "2026-08-13" },
      { id: 5, date: "2026-08-13" },
      { id: 3, date: "2026-08-12" },
    ]);
    expect(ordinals.get(5)).toBe(1);
    expect(ordinals.get(8)).toBe(2);
    expect(ordinals.get(3)).toBe(1);
  });

  it("gives every day that ran once the same answer", () => {
    const ordinals = cycleOrdinals([
      { id: 2, date: "2026-08-12" },
      { id: 1, date: "2026-08-11" },
    ]);
    expect([...ordinals.values()]).toEqual([1, 1]);
  });

  it("counts a day run three times", () => {
    const ordinals = cycleOrdinals([
      { id: 30, date: "2026-08-13" },
      { id: 10, date: "2026-08-13" },
      { id: 20, date: "2026-08-13" },
    ]);
    expect([ordinals.get(10), ordinals.get(20), ordinals.get(30)]).toEqual([1, 2, 3]);
  });

  it("is empty for no rows", () => {
    expect(cycleOrdinals([]).size).toBe(0);
  });

  it("agrees between a full record and a phase's slice of it", () => {
    // The two call sites render overlapping subsets of the same rows. The
    // ordinal is a fact about the row, so it is computed once over everything
    // — a row cannot be the 2nd cycle in the record and the 1st in the
    // drill-in. This is the case that breaks if the map is ever built from a
    // filtered list: id 5 is IDEA, id 8 is VALIDATION, same date.
    const all = [
      { id: 8, date: "2026-08-13", phase: "VALIDATION" },
      { id: 5, date: "2026-08-13", phase: "IDEA" },
    ];
    const ordinals = cycleOrdinals(all);
    const drillIn = all.filter((r) => r.phase === "VALIDATION");
    expect(ordinals.get(drillIn[0].id)).toBe(2);
  });
});

describe("newestFirst", () => {
  it("puts a day's last cycle first, and counts down", () => {
    // The order the marker has to agree with: numbered rows reading 4th, 1st,
    // 2nd, 3rd is what the server's `-date`-only ordering produces.
    const sorted = newestFirst([
      { id: 20, date: "2026-08-13" },
      { id: 17, date: "2026-08-13" },
      { id: 18, date: "2026-08-13" },
      { id: 19, date: "2026-08-13" },
    ]);
    expect(sorted.map((r) => r.id)).toEqual([20, 19, 18, 17]);
  });

  it("keeps dates newest first across the whole list", () => {
    const sorted = newestFirst([
      { id: 1, date: "2026-08-09" },
      { id: 5, date: "2026-08-13" },
      { id: 3, date: "2026-08-11" },
    ]);
    expect(sorted.map((r) => r.date)).toEqual(["2026-08-13", "2026-08-11", "2026-08-09"]);
  });

  it("reverses the ordinals exactly", () => {
    // The two functions read the same sequence from opposite ends, and this is
    // the property that keeps them honest about each other.
    const rows = [
      { id: 30, date: "2026-08-13" },
      { id: 10, date: "2026-08-13" },
      { id: 20, date: "2026-08-13" },
    ];
    const ordinals = cycleOrdinals(rows);
    expect(newestFirst(rows).map((r) => ordinals.get(r.id))).toEqual([3, 2, 1]);
  });

  it("does not sort the caller's array", () => {
    const rows = [
      { id: 1, date: "2026-08-09" },
      { id: 2, date: "2026-08-13" },
    ];
    newestFirst(rows);
    expect(rows.map((r) => r.id)).toEqual([1, 2]);
  });
});

describe("ordinalLabel", () => {
  it("writes the ordinals a record actually reaches", () => {
    expect([1, 2, 3, 4, 5].map(ordinalLabel)).toEqual(["1st", "2nd", "3rd", "4th", "5th"]);
  });

  it("does not write 11st", () => {
    // Eleven cycles in one day is permitted by the model, so it is reachable.
    expect([11, 12, 13, 21, 22, 23].map(ordinalLabel)).toEqual([
      "11th",
      "12th",
      "13th",
      "21st",
      "22nd",
      "23rd",
    ]);
  });
});

describe("rowsExtent", () => {
  it("takes both ends from the rows, in any order", () => {
    expect(
      rowsExtent([
        { date: "2026-07-18" },
        { date: "2026-07-09" },
        { date: "2026-07-11" },
      ]),
    ).toEqual({ start: "2026-07-09", end: "2026-07-18", days: 3, cycles: 3 });
  });

  it("counts days and cycles apart when a day was run twice", () => {
    // The reason the heading cannot call its rows "days": three rows, two
    // days. Both numbers are true and they are not the same number.
    expect(
      rowsExtent([
        { date: "2026-08-13" },
        { date: "2026-08-13" },
        { date: "2026-08-12" },
      ]),
    ).toEqual({ start: "2026-08-12", end: "2026-08-13", days: 2, cycles: 3 });
  });

  it("gives one day both ends", () => {
    expect(rowsExtent([{ date: "2026-08-14" }])).toEqual({
      start: "2026-08-14",
      end: "2026-08-14",
      days: 1,
      cycles: 1,
    });
  });

  it("returns null rather than a range for no rows", () => {
    // The caller's empty branch says "No check-ins recorded in this phase",
    // and a heading over nothing must not print a date.
    expect(rowsExtent([])).toBeNull();
  });
});

/** What these protect: which rows the record card shows, and whether the cycle
 * column is drawn beside them. Both were expressions inside the card's JSX,
 * and the second one is drawn twice — the record and the phase drill-in ask it
 * of different row sets and must get the same answer about the same row. */
describe("anyRepeat", () => {
  const week = [
    { id: 11, date: "2026-08-14" },
    { id: 10, date: "2026-08-13" },
    { id: 9, date: "2026-08-13" },
    { id: 8, date: "2026-08-12" },
  ];
  const ordinals = cycleOrdinals(week);

  it("is false on a record where every day ran once", () => {
    // The ordinary case, and the reason this is asked at all: a column reading
    // "1st" down every row says nothing and costs width on a 360px phone.
    expect(anyRepeat([week[0], week[3]], ordinals)).toBe(false);
  });

  it("is true when a day in view was run twice", () => {
    expect(anyRepeat(week, ordinals)).toBe(true);
  });

  it("is asked of the rows shown, not of the whole record", () => {
    // The drill-in's rows. A repeat three months ago is not something the
    // reader of this week can see, and a column drawn for it would read as if
    // these rows were the repeats.
    expect(anyRepeat([week[0]], ordinals)).toBe(false);
    // But the ordinal itself still comes from the whole set: row 10 is the 2nd
    // cycle of its day wherever it is shown, which is why the map is passed in
    // rather than recomputed over the slice.
    expect(anyRepeat([week[0], week[1]], ordinals)).toBe(true);
  });

  it("is false over no rows", () => {
    expect(anyRepeat([], ordinals)).toBe(false);
  });
});

describe("recordSlice", () => {
  // Nine rows over eight days — the oldest day was run twice — so the preview
  // of seven cuts the record above the repeat.
  const rows = [
    { id: 1, date: "2026-08-06" },
    { id: 2, date: "2026-08-06" },
    { id: 3, date: "2026-08-07" },
    { id: 4, date: "2026-08-08" },
    { id: 5, date: "2026-08-09" },
    { id: 6, date: "2026-08-10" },
    { id: 7, date: "2026-08-11" },
    { id: 8, date: "2026-08-12" },
    { id: 9, date: "2026-08-13" },
  ];
  const ordinals = cycleOrdinals(rows);

  it("shows the newest rows first, capped at the preview", () => {
    const { shown } = recordSlice(rows, ordinals, false, 7);
    expect(shown.map((r) => r.id)).toEqual([9, 8, 7, 6, 5, 4, 3]);
  });

  it("counts rows, not days", () => {
    // A builder who declares a second task after proving the first gets two
    // rows for one date. This record is nine rows over eight days, and a cap
    // that meant DAYS would have to decide which of the 6th's two cycles to
    // drop. Rows is what the card can actually deliver.
    const { shown } = recordSlice(rows, ordinals, true, 7);
    expect(shown).toHaveLength(9);
    expect(new Set(shown.map((r) => r.date)).size).toBe(8);
  });

  it("shows everything once the reader asks", () => {
    const { shown } = recordSlice(rows, ordinals, true, 7);
    expect(shown).toHaveLength(9);
    expect(shown[0].id).toBe(9);
    // Newest first inside a date as well as across dates: the 6th's second
    // cycle sits above its first.
    expect(shown[7].id).toBe(2);
    expect(shown[8].id).toBe(1);
  });

  it("draws the cycle column only when a shown row is a repeat", () => {
    // The 6th of August ran twice. It is outside the preview and inside the
    // full record, so the same rows give two different answers — which is the
    // behaviour, not a bug: the column is about what is on screen.
    expect(recordSlice(rows, ordinals, false, 7).showCycle).toBe(false);
    expect(recordSlice(rows, ordinals, true, 7).showCycle).toBe(true);
  });

  it("leaves the caller's array alone", () => {
    // `rows` is React state. Sorting it in place would mutate a payload the
    // rest of the render is still reading.
    const before = rows.map((r) => r.id);
    recordSlice(rows, ordinals, true, 7);
    expect(rows.map((r) => r.id)).toEqual(before);
  });

  it("is empty on a goal with no days yet", () => {
    expect(recordSlice([], new Map(), false, 7)).toEqual({ shown: [], showCycle: false });
  });
});
