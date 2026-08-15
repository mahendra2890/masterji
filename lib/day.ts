// What today's loop is doing, computed from today's row.
//
// Five rules the daily card and the phone's pane both act on: whether the day
// is still open, whether tonight's half is on screen, and which of three
// sentences the composer note shows. Every one of them was an expression
// inside JSX in a 3,600-line component, which is the one file in the frontend
// no test can reach — so the rules that decide what a builder is shown each
// evening were the least pinned code in the app.
//
// Pure and separate for the reason #117 settled, and stated again by
// lib/record.ts: this is decidable arithmetic over data the payload already
// holds, so it is pinned here, and the JSX that renders the answer is driven
// in a browser.

import type { CheckIn } from "./coach-api";

/** The parts of a check-in these rules read, and only those.
 *
 * Structural rather than `CheckIn` so a test states the four fields under
 * test instead of twenty it has no opinion about — the same bargain
 * `record.ts`'s `Cycle` makes. A real `CheckIn` satisfies it, which is what
 * keeps the component honest.
 */
export type TodayFacts = {
  amDeclaration: string;
  pmProofText: string;
  proofStatus: CheckIn["proofStatus"];
  proofOffer: string;
  proofMissing: string;
  /** Earlier tries at tonight's proof, oldest first. Only the count is read. */
  attempts: readonly unknown[];
};

/** A proof is filed and the cycle is not finished with it. Two ways in, and
 * they are opposites: Masterji read it and wants more (PUSHED_BACK), or he
 * never read it at all (UNJUDGED). Both leave tonight open and both keep the
 * proof box on screen, so every test that used to name PUSHED_BACK alone asks
 * this instead.
 *
 * Mirrors views.UNSETTLED, which decides the same thing for the server — if
 * these two ever disagree, the card and the endpoint disagree about whether
 * the evening is over. `day.test.ts` reads that tuple out of
 * `backend/coach/views.py` and compares it against this, so the invariant is
 * checked rather than restated.
 */
export function isUnsettled(status: CheckIn["proofStatus"]): boolean {
  return status === "PUSHED_BACK" || status === "UNJUDGED";
}

/** The pieces tonight's draft still owes, as the server listed them — one
 * phrase per piece, semicolons between. Split in one place because two screens
 * read it: the Today card lists them, and the line over the composer counts
 * them for a builder who is on the other pane. */
export function missingPieces(missing: string): string[] {
  return missing
    .split(";")
    .map((piece) => piece.trim())
    .filter(Boolean);
}

/** Today's loop is still open — worth a dot on the pane you can't see.
 *
 * No row at all is open, not closed: a builder who has not declared yet has
 * the whole day ahead of them, and the branch that decides this used to lean
 * on `!today?.amDeclaration` reading `undefined` as falsy. Said out loud here
 * so it survives a rewrite that reaches for `??`.
 */
export function dayOpen(today: TodayFacts | null | undefined): boolean {
  if (!today) return true;
  return !today.amDeclaration || !today.pmProofText || isUnsettled(today.proofStatus);
}

/** A FINISHED proof Masterji drafted out of the conversation and nobody has
 * filed. Distinct from `dayOpen` on purpose: `dayOpen` is lit from the moment
 * the day starts, so it cannot announce anything that arrives mid-day.
 *
 * Running notes deliberately don't light it. The dot means "there is something
 * on the other pane for you to do", and notes are the evening's working-out —
 * they'd relight it on nearly every turn and teach the builder that the dot
 * means nothing.
 *
 * Reads `proofMissing` raw rather than through `missingPieces`, and that is
 * not an inconsistency with `notesRunning` below: a draft with any missing
 * text against it is not finished, whether or not that text names a piece.
 */
export function draftWaiting(today: TodayFacts | null | undefined): boolean {
  return dayOpen(today) && Boolean(today?.proofOffer) && !today?.proofMissing;
}

/** Notes still being gathered: he has part of tonight's proof written down and
 * has said which pieces are outstanding. Not `draftWaiting` — there is nothing
 * to file yet — but emphatically not nothing, which is what the chat pane told
 * the builder for as long as this state existed. The whole point of running
 * notes is that they can SEE they were heard, and the one surface they were
 * looking at while being heard denied it. */
export function notesRunning(today: TodayFacts | null | undefined): boolean {
  const owed = today?.proofMissing ? missingPieces(today.proofMissing) : [];
  return dayOpen(today) && Boolean(today?.proofOffer) && owed.length > 0;
}

/** The hour the evening half of the Today card stops being folded away.
 *
 * Declaring at nine in the morning used to hand the builder the whole evening
 * back in the same breath — the ask, the box, the link field, the attach
 * control and "Submit proof", four-fifths of the card, for work that cannot
 * happen for another ten hours. The product sells two minutes a day and the
 * screen after those two minutes looked like homework.
 *
 * Local, and deliberately the same local day the check-in itself is stamped
 * with (see CheckIn.date) — this is the builder's evening, not the server's.
 * Read at render rather than pinned at mount, so a card left open on a desk
 * since morning has caught up by the time anyone looks at it again. That is
 * why the hour is an argument here: the caller keeps the property, and a test
 * can drive both sides of it.
 *
 * Five is early for an evening on purpose. Being an hour too eager costs a
 * builder one fold they can ignore; being an hour too late costs them the
 * proof, because the card would be hiding the only box that counts at the
 * moment they came to use it.
 */
export const EVENING_FROM = 17;

/** Whether the Today card is showing tonight's half yet.
 *
 * Every clause but the clock is an evening that has already started, so the
 * only builder who meets the folded card is one who declared this morning and
 * has done nothing since — which is exactly who it is for. A push-back is owed
 * work; an earlier try means they were here tonight already; and any
 * proofOffer at all, finished or still gathering, means Masterji has been
 * writing this evening down and hiding that would undo what the running notes
 * are for.
 *
 * `filingNow` is the builder's own press — finished early, or filing at four
 * because they're out at seven. It only ever forces the half OPEN, which is
 * why it is first and why nothing here can close it again.
 *
 * `hour` is the builder's own clock, 0–23.
 */
export function eveningOpen(
  today: TodayFacts | null | undefined,
  hour: number,
  filingNow: boolean,
): boolean {
  if (filingNow) return true;
  if (!today?.amDeclaration) return true;
  return (
    isUnsettled(today.proofStatus) ||
    today.attempts.length > 0 ||
    Boolean(today.proofOffer) ||
    hour >= EVENING_FROM
  );
}
