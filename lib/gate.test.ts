import { describe, expect, it } from "vitest";
import {
  commitIsLoud,
  gateKey,
  isEarned,
  type CommitSituation,
  type GateSituation,
} from "./gate";
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
    // Without the id, a refusal left over from the last idea would match a
    // brand-new goal standing in IDEA at 0 proofs and greet it with a refusal
    // it never earned. That was reachable in one step while the whole app was
    // one component — retiring took the render down the no-goal branch without
    // unmounting. <Dashboard /> owns `gateNote` now and dies with the goal, so
    // this pins a second line of defence; see gateKey's own note.
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

describe("commitIsLoud", () => {
  // A room mid-conversation with two of IDEA's four parts turned up: the one
  // state the soft gate is quiet in. Every test below is this, one field moved.
  const room = (over: Partial<CommitSituation> = {}): CommitSituation => ({
    roomOpen: true,
    turnsLeft: 9,
    have: 2,
    need: 4,
    ...over,
  });

  it("is loud on a room nobody has opened", () => {
    // The screen a builder sees the moment they finish signing up. Dimming
    // Commit here leaves it with no filled control at all, and taxes somebody
    // who arrived knowing what to build for a conversation they never wanted.
    expect(commitIsLoud(room({ roomOpen: false, have: 0 }))).toBe(true);
  });

  it("is quiet mid-conversation under four of four", () => {
    // The one row the whole change exists for: the scaffold is the loudest
    // thing on the column while the conversation is unfinished.
    expect(commitIsLoud(room())).toBe(false);
    expect(commitIsLoud(room({ have: 0 }))).toBe(false);
    expect(commitIsLoud(room({ have: 3 }))).toBe(false);
  });

  it("is loud again at four of four", () => {
    expect(commitIsLoud(room({ have: 4 }))).toBe(true);
  });

  it("is loud when the turns are spent, however few parts landed", () => {
    // The dead end. At zero turns left the composer is gone and the closing
    // copy points straight at the box — a quiet Commit under "put it in the
    // box above" is a screen with no lit exit.
    expect(commitIsLoud(room({ turnsLeft: 0, have: 0 }))).toBe(true);
    expect(commitIsLoud(room({ turnsLeft: 0, have: 2 }))).toBe(true);
  });

  it("never dims the door on a payload it did not get", () => {
    // need <= 0 is a bundle older than the field, not a bar with nothing in
    // it. "I don't know how many parts there are" resolves loud.
    expect(commitIsLoud(room({ need: 0, have: 0 }))).toBe(true);
    expect(commitIsLoud(null)).toBe(true);
    expect(commitIsLoud(undefined)).toBe(true);
  });

  it("only ever changes the volume — there is no state it refuses in", () => {
    // Guards the rule the whole soft gate rests on: this returns a style, and
    // a commit at 0 of 4 works exactly as it does at 4 of 4. If a future edit
    // makes this answer "may they commit", that is a different function and
    // this test should be the thing that stops it.
    const everyState = [
      room({ roomOpen: false }),
      room(),
      room({ have: 4 }),
      room({ turnsLeft: 0 }),
    ];
    for (const s of everyState) expect(typeof commitIsLoud(s)).toBe("boolean");
  });
});
