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

import type { Gate } from "./coach-api";

export function isEarned(gate: Gate | null | undefined): boolean {
  if (!gate || gate.need <= 0) return false;
  return gate.have >= gate.need && gate.owed.length === 0;
}
