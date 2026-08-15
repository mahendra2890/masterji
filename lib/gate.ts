// Whether the bar is met — the one rule, in one place.
//
// It has two readers on the goal card now: the sentence ("Earned. BUILD is
// yours to open." over a button that opens it) and the meter, which turns green
// on exactly the same condition. Two copies of `have >= need && !owed.length`
// would be two chances for the colour and the words to disagree, and the
// disagreement that matters is one-directional — a green bar under a card that
// still says "Request phase advance" is a lit door that does not open, on the
// product's own word.
//
// `owed` is why this is not just have >= need. BUILD asks for two proofs AND
// one of them being a real user touching the thing, so the count can be full
// while the phase is not met. The server is the authority either way: this
// reads numbers gates.py sent and never recomputes them.

import type { Gate, Phase } from "./coach-api";

export function isEarned(gate: Gate | null | undefined): boolean {
  if (!gate || gate.need <= 0) return false;
  return gate.have >= gate.need && gate.owed.length === 0;
}

/** The gate situation a note was an answer to.
 *
 * "Not yet, 0/1" stops being true the moment a proof lands, and the card used
 * to keep saying it — under a bar that had since filled, which is the worst
 * sentence to be reading at the best moment in the product. Pinning each
 * answer to the state that produced it lets the card tell that it has been
 * overtaken instead of asserting a refusal the database no longer agrees with.
 *
 * The goal id is in it because the component survives a goal ending: retiring
 * takes the render down the no-goal branch without unmounting, so a refusal
 * left over from the last idea would match a brand-new goal standing in IDEA
 * at 0 proofs and greet it with a refusal it never earned.
 *
 * The row count is in it for the same reason on a phase that counts people: a
 * second conversation with the same person moves `banked` and not `have`, and
 * the refusal quotes both numbers. Keyed on `have` alone it would sit there
 * saying "3 accepted proofs" over a record that now holds four.
 *
 * Each of the four fields is therefore a bug that has already happened once.
 * Nothing about a string comparison can tell you a fifth is needed, but
 * `gate.test.ts` pins all four against the state changes they were added for,
 * so dropping one is a failing test rather than a refusal outliving its cause.
 */
/** The four things the key is made of, and nothing else — `CoachState`
 * satisfies it. Structural so a test can state the situation under test rather
 * than a whole payload, the same bargain `isEarned` makes by taking `Gate`. */
export type GateSituation = {
  goal: { id: number; phase: Phase } | null;
  gate: Pick<Gate, "have" | "banked"> | null;
};

export function gateKey(s: GateSituation | null | undefined): string {
  return s?.goal
    ? `${s.goal.id}:${s.goal.phase}:${s.gate?.have ?? 0}:${s.gate?.banked ?? 0}`
    : "";
}

/** The workshop's soft gate: whether Commit is the loud control right now.
 *
 * The room drives at all four of IDEA's parts, and the screen is what carries
 * that opinion — never the server and never the coach. Nothing is disabled,
 * nothing is refused, and a commit at 0 of 4 works exactly as it does at 4 of
 * 4. What changes is where the eye goes: while the conversation is unfinished
 * the scaffold is the loudest thing on the column, and Commit renders
 * secondary.
 *
 * It lives here rather than in the JSX for the reason `isEarned` does. This is
 * the same failure shape one screen later — a quiet Commit under closing copy
 * that says "put it in the box above" is a dead-end screen, the way a green bar
 * over "Request phase advance" is a lit door that does not open — and it has
 * one more state in it than a boolean expression in a className wants to hold.
 *
 * The whole table, which `gate.test.ts` pins row by row:
 *
 *   | room         | sketch    | Commit |
 *   | never opened | —         | LOUD   |
 *   | open         | under 4/4 | quiet  |
 *   | open         | 4/4       | LOUD   |
 *   | turns spent  | any       | LOUD   |
 *
 * Row 1 is why this takes `roomOpen` at all. Unconditional, the gate leaves the
 * screen a builder sees the moment they finish signing up with no filled
 * control on it — and it taxes the wrong person, since somebody who arrived
 * knowing what to build never wanted the room and would find their one action
 * dimmed over a conversation they had no reason to have. The gate says "this
 * conversation is unfinished", not "you haven't talked to him yet".
 *
 * Row 4 is the dead end, and it is the row with a real failure in it. At zero
 * turns left the composer is gone and the closing copy points straight at the
 * box; a secondary Commit under "Put it in the box above" is a screen with no
 * lit exit.
 */
export type CommitSituation = {
  /** Whether the builder has actually said something in the room. A room that
   * exists because a page loaded is not an opened one. */
  roomOpen: boolean;
  /** Turns left in the room. 0 means spent — the composer is gone by then. */
  turnsLeft: number;
  /** IDEA's parts turned up so far, and how many there are. */
  have: number;
  need: number;
};

export function commitIsLoud(s: CommitSituation | null | undefined): boolean {
  if (!s || !s.roomOpen) return true;
  if (s.turnsLeft <= 0) return true;
  // `need <= 0` is a payload that never arrived rather than a bar with nothing
  // in it, and the safe reading of "I don't know how many parts there are" is
  // the loud one: this must never dim the only door on a guess.
  if (s.need <= 0) return true;
  return s.have >= s.need;
}
