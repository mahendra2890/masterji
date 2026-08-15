import { describe, expect, it } from "vitest";
import { saidBefore } from "./messages";

type Row = { role: "USER" | "COACH" | "SYSTEM"; content: string };

const log = (...rows: [Row["role"], string][]): Row[] =>
  rows.map(([role, content]) => ({ role, content }));

/** What these protect: this feeds a button that SENDS. Putting somebody else's
 * sentence in the builder's mouth is the one failure it cannot have, and the
 * cheap version — reading `i - 1` — has it, because "the row above" is an
 * assumption about how the server writes rows rather than the question being
 * asked. */
describe("saidBefore", () => {
  it("is the builder's turn above a notice", () => {
    const rows = log(["USER", "how do I find people"], ["SYSTEM", "that one didn't go through"]);
    expect(saidBefore(rows, 1)).toBe("how do I find people");
  });

  it("searches past whatever sits between", () => {
    // A notice can be written after a COACH row — a turn that streamed part of
    // an answer and then failed — and after another notice, when the retry
    // failed too. `i - 1` would re-send Masterji's own words in the first case
    // and a system string in the second.
    const rows = log(
      ["USER", "how do I find people"],
      ["COACH", "Start with the ten nearest you."],
      ["SYSTEM", "that one didn't go through"],
      ["SYSTEM", "that one didn't go through"],
    );
    expect(saidBefore(rows, 3)).toBe("how do I find people");
  });

  it("is empty when the builder has said nothing yet", () => {
    // The digest on the first visit of a new week is written above any turn.
    // Empty means no retry button, which is right for a notice with nothing
    // behind it rather than a button that would send "".
    expect(saidBefore(log(["SYSTEM", "your week, read back"]), 0)).toBe("");
    expect(saidBefore([], 0)).toBe("");
  });

  it("takes the LAST thing they said, not the first", () => {
    const rows = log(
      ["USER", "first question"],
      ["COACH", "an answer"],
      ["USER", "second question"],
      ["SYSTEM", "that one didn't go through"],
    );
    expect(saidBefore(rows, 3)).toBe("second question");
  });
});
