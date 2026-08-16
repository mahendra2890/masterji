// Where the conversation renders the commit moment, and when it stops.
//
// Whenever the Today card would show a draft with its fill control, the chat
// log shows the same draft with the commit control in place: `Declare it` under
// a drafted task, `Submit proof` under tonight's draft. What dies is the pane
// switch — on a phone the two panes take turns, so a draft finished in the
// conversation used to land in the pane the builder was not looking at, and the
// product narrated the errand it had created ("file it under Today").
//
// The rule this file exists to make STRUCTURAL:
//
//   **The card is state-driven, never message-driven.**
//
// It renders from the live offer — `declarationOffer` / `CheckIn.proofOffer`,
// which the server only ever serves for today — keyed to a position in the
// transcript. It is NOT part of the message it arrived beside, and nothing in
// the transcript holds a copy of it. The moment the offer is filed, replaced or
// expires, every card that pointed at it stops being a control.
//
// #219 is the failure class that rule keeps out: Masterji offering a door he
// cannot open and then saying he walked through it. A `Declare it` button still
// sitting in scrollback after the day settled is that same shape — and
// yesterday's card declaring today would be worse, because it would work.
//
// So the mechanism is not "remember to hide it". Three separate facts have to
// agree before anything draws at all:
//
//   1. There is a live offer right now (`liveOffer`, read off the same state
//      the Today card branches on — so the two surfaces cannot disagree).
//   2. The anchor's key still matches that offer's identity (`liveAnchor`).
//      Filing it, or a rewritten draft, changes the identity and the old
//      position goes dark.
//   3. The anchor was laid down on the builder's own local date, today.
//      A tab left open past midnight cannot press yesterday's draft into
//      tonight's row.
//
// Pure and separate for the reason lib/day.ts and lib/record.ts already give:
// this is decidable arithmetic over data the payload holds, so it is pinned
// here, and the JSX that renders the answer is driven in a browser.

import type { CheckIn } from "./coach-api";

/** Which of the two daily writes a card is offering. */
export type OfferKind = "declare" | "prove";

/** A draft the conversation may render with its commit control.
 *
 * `key` is the draft's identity, and everything above turns on it. Two offers
 * with the same key are the same draft; anything that changes what the card
 * would show changes the key, which retires every card drawn against the old
 * one.
 */
export type LiveOffer = {
  kind: OfferKind;
  key: string;
  text: string;
  /** Prove only: what the draft still lacks, as the server listed it. "" on a
   * draft that clears the bar, and always "" on a declaration. */
  missing: string;
  /** Prove only: today's reading of the one number, as Masterji heard it said.
   * null on most evenings and on every declaration. */
  metric: number | null;
};

/** Where a card is drawn, and when it was laid down.
 *
 * Deliberately inert: a place and a day, with no draft in it. The offer is read
 * live on every render, so an anchor can only ever point at one — it can never
 * BE one, which is what stops a card outliving the thing it commits.
 */
export type OfferAnchor = {
  key: string;
  /** The newest message in the log when this offer first arrived, so the card
   * lands under the words that drafted it. null when the log was empty. */
  afterMessageId: number | null;
  /** The builder's own local date, the day the anchor was laid down. */
  date: string;
};

/** The parts of today's row these rules read, and only those — the same bargain
 * `TodayFacts` makes in lib/day.ts, so a test states six fields rather than
 * twenty it has no opinion about. A real `CheckIn` satisfies it. */
export type OfferToday = {
  id: number;
  amDeclaration: string;
  pmProofText: string;
  proofStatus: CheckIn["proofStatus"];
  proofOffer: string;
  proofMissing: string;
  metricOffer: number | null;
};

/** Both surfaces read the same fields, and this is all of them. */
export type OfferFacts = {
  /** CoachState.declarationOffer — top-level, because at the moment it is
   * written there is no check-in to hang it on. */
  declarationOffer: string;
  today: OfferToday | null;
};

/** A proof is filed and the cycle is not finished with it. The same tuple
 * lib/day.ts pins against views.UNSETTLED; imported rather than restated would
 * be better still, and it is — see the import in Dashboard. Kept local here so
 * this module has one dependency and it is a type. */
function unsettled(status: CheckIn["proofStatus"]): boolean {
  return status === "PUSHED_BACK" || status === "UNJUDGED";
}

/** The draft the Today card would be showing with its fill control, or null.
 *
 * Every branch below is the Today card's own branch, in its own order, and that
 * is the point: "whenever the Today card would show a draft" is the issue's
 * wording, and two surfaces reading two conditions is how they come to disagree
 * about whether a control exists.
 *
 * The evening deliberately does not consult `eveningOpen`. It cannot matter:
 * `eveningOpen` returns true for any non-empty `proofOffer`, so a proof draft
 * always has the evening half of the card open under it. Saying so here rather
 * than passing the hour in keeps the clock out of a pure identity.
 */
export function liveOffer(facts: OfferFacts): LiveOffer | null {
  const today = facts.today;
  // The morning. The declaration draft lives on the goal precisely because no
  // check-in exists until Declare it is pressed, and the card renders it only
  // in the branch with nothing declared — so it can never appear where
  // "Declared:" goes. DeclareView spends the offer server-side on the same
  // write, so this is belt and braces rather than the only guard.
  if (!today?.amDeclaration) {
    if (!facts.declarationOffer) return null;
    return {
      kind: "declare",
      key: `declare:${facts.declarationOffer}`,
      text: facts.declarationOffer,
      missing: "",
      metric: null,
    };
  }
  // The evening, on the card's second branch: a cycle still owing its proof.
  // A settled verdict closes it, and an unsettled one (pushed back, or filed
  // and unread) leaves tonight open with the draft still on the row.
  if (today.pmProofText && !unsettled(today.proofStatus)) return null;
  if (!today.proofOffer) return null;
  return {
    kind: "prove",
    // The check-in as well as the words: a second cycle on one day is a
    // different task under the same date, and its draft must not inherit the
    // first one's position in the log. `missing` and the number are in here
    // because the card draws them — a rewritten draft is a different offer,
    // and the card that showed the old one has to go dark rather than move.
    key: `prove:${today.id}:${today.proofMissing}:${today.metricOffer ?? ""}:${today.proofOffer}`,
    text: today.proofOffer,
    missing: today.proofMissing,
    metric: today.metricOffer,
  };
}

/** The anchor to hold after this render.
 *
 * Same key: the anchor is returned unchanged, including its date. That is the
 * day-boundary rule, and it is worth being explicit that it is a rule rather
 * than an oversight — an anchor laid down yesterday STAYS stamped yesterday, so
 * `liveAnchor` below refuses it for as long as it exists. Re-stamping it here
 * would be the one line that lets yesterday's card declare today.
 *
 * It cannot strand a genuinely live offer. The server serves a declaration
 * draft only under the date the request was sent, and a proof draft's key
 * carries the check-in id, so a new day is a new key or no offer at all — and
 * no offer clears the anchor, which lets the next one anchor fresh.
 */
export function nextAnchor(
  anchor: OfferAnchor | null,
  key: string | null,
  newestMessageId: number | null,
  date: string,
): OfferAnchor | null {
  if (key === null) return null;
  if (anchor && anchor.key === key) return anchor;
  return { key, afterMessageId: newestMessageId, date };
}

/** The anchor a card may actually be drawn against, or null.
 *
 * Null is a card that is not there — not a disabled one. A control that has
 * stopped being a control should stop being on screen, because a greyed-out
 * `Declare it` in last Tuesday's scrollback is still an offer of a door.
 */
export function liveAnchor(
  anchor: OfferAnchor | null,
  key: string | null,
  date: string,
): OfferAnchor | null {
  if (!anchor || key === null) return null;
  // Filed, or replaced by a rewritten draft. Either way this position is
  // pointing at something that no longer exists.
  if (anchor.key !== key) return null;
  // A day boundary crossed under an open tab.
  if (anchor.date !== date) return null;
  return anchor;
}

/** Which message the card is drawn after, as an index into the log.
 *
 * -1 means "before the first message", which is a log with nothing in it yet.
 * A message the payload no longer carries falls back to the tail: the state
 * payload is capped, so a long conversation eventually trims the turn the
 * draft arrived beside, and a card that vanished because its neighbour aged
 * out would be the live offer losing its only inline surface.
 */
export function cardIndex(
  anchor: OfferAnchor | null,
  ids: readonly number[],
): number | null {
  if (!anchor) return null;
  const at = ids.indexOf(anchor.afterMessageId ?? -1);
  return at === -1 ? ids.length - 1 : at;
}
