import { describe, expect, it } from "vitest";
import { gateKey, isEarned, type GateSituation } from "./gate";
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

const situation = (over: Partial<GateSituation> = {}): GateSituation => ({
  goal: { id: 7, phase: "VALIDATION" },
  gate: { have: 1, banked: 1 },
  ...over,
});

/** What these protect: a refusal is a sentence about a moment — "Not yet,
 * 0/1" — and the card keeps showing it until the moment is over. `gateKey`
 * decides when it is over, and each of its four fields is a bug that already
 * happened: a refusal outliving the proof that answered it, a dead goal's
 * refusal greeting a brand-new goal, and one quoting `have` while `banked`
 * moved underneath it.
 *
 * The failure these cannot catch is a FIFTH field being needed — nothing about
 * a string comparison can tell you the situation has a part it isn't reading.
 * What they can catch is one of the four being dropped, which is the change a
 * later reader is actually likely to make: each test below moves exactly one
 * field and asserts the key moves with it, so removing that field from the
 * template fails here rather than in front of a builder. */
describe("gateKey", () => {
  it("is stable while nothing about the situation has changed", () => {
    // The other half of the rule, and the reason it is not a counter: the note
    // has to survive every refetch that changes nothing, or it would blink out
    // on the poll after it was written.
    expect(gateKey(situation())).toBe(gateKey(situation()));
  });

  it("moves when a proof lands", () => {
    // "Not yet, 0/1" under a bar that has since filled is the worst sentence to
    // be reading at the best moment in the product.
    expect(gateKey(situation({ gate: { have: 0, banked: 0 } }))).not.toBe(
      gateKey(situation({ gate: { have: 1, banked: 1 } })),
    );
  });

  it("moves when only `banked` moves", () => {
    // VALIDATION counts PEOPLE. A second conversation with the same person
    // moves `banked` and not `have`, and the refusal quotes both numbers —
    // keyed on `have` alone it would sit there saying "3 accepted proofs" over
    // a record that now holds four.
    expect(gateKey(situation({ gate: { have: 3, banked: 3 } }))).not.toBe(
      gateKey(situation({ gate: { have: 3, banked: 4 } })),
    );
  });

  it("moves when the phase does", () => {
    expect(gateKey(situation({ goal: { id: 7, phase: "VALIDATION" } }))).not.toBe(
      gateKey(situation({ goal: { id: 7, phase: "BUILD" } })),
    );
  });

  it("moves when the goal does, even into the same phase at the same count", () => {
    // The component survives a goal ending — retiring takes the render down the
    // no-goal branch without unmounting. Without the id, a refusal left over
    // from the last idea would match a brand-new goal standing in IDEA at 0
    // proofs and greet it with a refusal it never earned.
    const dead = { goal: { id: 7, phase: "IDEA" as const }, gate: { have: 0, banked: 0 } };
    const fresh = { goal: { id: 8, phase: "IDEA" as const }, gate: { have: 0, banked: 0 } };
    expect(gateKey(dead)).not.toBe(gateKey(fresh));
  });

  it("is empty with no goal, and never matches a real situation", () => {
    // The no-goal screen. A note keyed "" must not be rendered over any goal,
    // which is what an empty key buys: nothing with a goal can produce it.
    expect(gateKey({ goal: null, gate: null })).toBe("");
    expect(gateKey(null)).toBe("");
    expect(gateKey(undefined)).toBe("");
    expect(gateKey(situation())).not.toBe("");
  });

  it("reads a missing gate as zero rather than dropping the goal", () => {
    // A phase with no bar (LAUNCH, TRACTION) sends no gate. The key still has
    // to name the goal and phase, or two of them would key alike.
    expect(gateKey({ goal: { id: 7, phase: "LAUNCH" }, gate: null })).toBe(
      gateKey({ goal: { id: 7, phase: "LAUNCH" }, gate: { have: 0, banked: 0 } }),
    );
    expect(gateKey({ goal: { id: 7, phase: "LAUNCH" }, gate: null })).not.toBe(
      gateKey({ goal: { id: 8, phase: "LAUNCH" }, gate: null }),
    );
  });
});
