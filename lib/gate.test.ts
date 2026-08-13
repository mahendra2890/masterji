import { describe, expect, it } from "vitest";
import { isEarned } from "./gate";
import type { Gate } from "./coach-api";

const gate = (over: Partial<Gate>): Gate => ({
  have: 0,
  need: 2,
  nextPhase: "LAUNCH",
  owed: [],
  banked: 0,
  ...over,
});

/** What these protect: the goal card reads this rule twice — once for the
 * words ("Earned. LAUNCH is yours to open.") and once for the colour of the
 * meter. They must never be able to disagree, and the expensive direction is a
 * green bar over a card that still says "Request phase advance". */
describe("isEarned", () => {
  it("is met when the count is there and nothing is owed", () => {
    expect(isEarned(gate({ have: 2, need: 2 }))).toBe(true);
    // Past the bar. The numerator is capped for display, never for this.
    expect(isEarned(gate({ have: 7, need: 2, banked: 7 }))).toBe(true);
  });

  it("is not met while a KIND is still owed, whatever the count says", () => {
    // BUILD's real shape: two proofs banked, and neither is a real user
    // touching the thing. The card says 2/2 and it is telling the truth —
    // this is the state where "Earned" would be a lit door that does not open.
    expect(
      isEarned(gate({ have: 2, need: 2, banked: 2, owed: ["a user touching it"] }))
    ).toBe(false);
  });

  it("is not met below the bar", () => {
    expect(isEarned(gate({ have: 0, need: 1 }))).toBe(false);
    expect(isEarned(gate({ have: 1, need: 3, banked: 3 }))).toBe(false);
  });

  it("is not met on a phase with no bar to meet", () => {
    // LAUNCH and TRACTION have no PROOFS_REQUIRED entry, so `need` is 0 and
    // the meter is not rendered at all. Earned-by-vacancy would be the wrong
    // answer if it ever were: nothing has been won by a phase asking nothing.
    expect(isEarned(gate({ have: 0, need: 0, nextPhase: null }))).toBe(false);
    expect(isEarned(gate({ have: 4, need: 0, banked: 4 }))).toBe(false);
  });

  it("is not met with no gate at all", () => {
    // The no-goal screen, and any payload old enough to be missing it.
    expect(isEarned(null)).toBe(false);
    expect(isEarned(undefined)).toBe(false);
  });
});
