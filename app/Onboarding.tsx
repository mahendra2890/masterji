"use client";

// The screen before there is a goal: the commit box, the room that helps
// somebody fill it, and — for a builder who has just closed one — what the
// closing said.
//
// Its own component so it owns its own hooks. It used to be an early return
// two thirds of the way down `Masterji()`, which made every hook in the app
// illegal below it; what is left of that shape is this file's short list of
// state at the top, all of which dies with the screen.

import { useRef, useState } from "react";
import Changelog from "@/components/Changelog";
import ClosedIdea from "./ClosedIdea";
import Workshop, { type RoomProps } from "./Workshop";
import { CLOSED_CHIP, SignOutButton, ToneSwitch, TourLink } from "./chrome";
import { commitIsLoud } from "@/lib/gate";
import { createGoal, type CoachState, type Retirement } from "@/lib/coach-api";
import styles from "./masterji.module.css";

/** Three goals of the right size, for the blank box on somebody's first day.
 *
 * The freeze there is not "I have no ideas" — it is not knowing how big the
 * box wants the answer to be, and a lone placeholder answers that with one
 * data point. Three answer it with a range: two of these are somebody else's
 * world entirely, which is the part that says "yours counts too" better than
 * any sentence could. Deliberately not the placeholder's tiffin app — a
 * fourth phrasing of the example already on screen teaches nothing, and that
 * one goes on to carry the whole guided tour.
 *
 * Kept in the worlds the playbooks and guidance.PROOF_EXAMPLES already talk
 * about — hostel floors, Instagram resellers, a building's own neighbours —
 * so a builder who taps one and reads the coaching afterwards lands somewhere
 * the product has already thought about. The last one earns its place by not
 * being software: nothing else on this screen says a first build is allowed
 * to be a spreadsheet and a WhatsApp group.
 */
const GOAL_EXAMPLES = [
  "Payment tracking for Instagram resellers",
  "A notice board for my hostel floor",
  "Weekend baking orders from my building",
];

export default function Onboarding({
  state,
  busy,
  error,
  run,
  refresh,
  justRetired,
  pivotFrom,
  setPivotFrom,
  onSetTone,
  room,
}: {
  state: CoachState;
  busy: boolean;
  error: string;
  run: (fn: () => Promise<void>) => Promise<void>;
  refresh: () => Promise<CoachState | null>;
  /** The goal that closed a moment ago, held by the parent because the screen
   * that sets it is the dashboard and the screen that reads it is this one.
   * That handover is what the `void justRetired;` line in the old single
   * component was standing in for. */
  justRetired: Retirement | null;
  /** Which closed goal the next one comes out of, set by "Same problem, new
   * idea" on the dashboard and spent by the commit here — the same handover,
   * in the same direction, for the same reason. */
  pivotFrom: number | null;
  setPivotFrom: (id: number | null) => void;
  onSetTone: (next: CoachState["tone"]) => void;
  room: RoomProps;
}) {
  const [goalTitle, setGoalTitle] = useState("");
  // The goal box, so the examples under it can put the caret in it.
  const goalBoxRef = useRef<HTMLInputElement>(null);
  // A closed idea being read back.
  const [viewClosed, setViewClosed] = useState<Retirement | null>(null);

  const { ws, roomTurnsLeft, wsPending } = room;

  const onCreateGoal = () =>
    run(async () => {
      if (!goalTitle.trim()) return;
      await createGoal(goalTitle.trim(), pivotFrom);
      setGoalTitle("");
      setPivotFrom(null);
      await refresh();
    });

  const closing = justRetired ?? state.archive[0];
  const shipped = closing?.outcome === "COMPLETED";
  // The box holds words that are theirs, not one of ours — see the buttons.
  const examplesSpent =
    goalTitle.trim() !== "" && !GOAL_EXAMPLES.includes(goalTitle);
  // Two columns once there is a conversation to put in the second one, and
  // the centred single column — the screen every builder lands on, tuned
  // against a real first impression — until then. The room's state (the
  // meter, the pile, the forecast) is the left column's with the box it
  // fills; the conversation is the right column's. That is the post-goal
  // shape, and this screen was holding all of it in one 520px stack with a
  // 320px window cut in the middle of it.
  const roomOpen = !!(ws?.messages.length || wsPending !== null);
  // The soft gate, decided in one place and read in two: the Commit button's
  // weight and the scaffold's. Not a permission — see commitIsLoud, which
  // holds the whole four-row table and the dead end at the bottom of it.
  const commitLoud = commitIsLoud({
    roomOpen,
    turnsLeft: roomTurnsLeft,
    have: ws?.sketch.have ?? 0,
    need: ws?.sketch.need ?? 0,
  });
  const sketchFull = !!ws && ws.sketch.need > 0 && ws.sketch.have >= ws.sketch.need;
  return (
    <main className={styles.onboarding} data-room={roomOpen ? "open" : "shut"}>
      {/* The commit side. Sticky at the top of its column so that every
          sentence the room produces pointing "up at the box" is true at the
          moment it is read: the closing line names it, `parkedLabel` says
          "tap to put it in the box", and WORKSHOP_SYSTEM tells the coach to
          say "the box is right there". Measured before this: at 375×812 with
          the turns spent, that closing line and the box it names were 913px
          apart on an 812px viewport, so the two could not be on screen
          together. It also strengthens the hierarchy the room was built
          around rather than weakening it — the box becomes the only
          permanently visible control on the screen. */}
    <div className={styles.commitSide}>
      <p className={styles.wordmark}>मास्टरजी</p>

      {closing ? (
        <>
          <h1 className={styles.onboardTitle}>
            {shipped ? "Shipped." : "Closed."}
          </h1>
          <p className={styles.closingWhich}>{closing.title}</p>
          <p
            className={
              closing.readsAs === "ACHIEVED" || closing.readsAs === "INVALIDATED"
                ? styles.closingWin
                : styles.closingPlain
            }
          >
            {closing.coachReaction}
          </p>
          <p className={styles.closingStats}>
            Reached {closing.phaseReached} · {closing.acceptedProofs} proof
            {closing.acceptedProofs === 1 ? "" : "s"} banked · {closing.daysActive}{" "}
            day{closing.daysActive === 1 ? "" : "s"} active
            {state.lifetimeDays > 0 && (
              <>
                {" · "}
                {state.lifetimeDays} day{state.lifetimeDays === 1 ? "" : "s"} of
                work on your record
              </>
            )}
          </p>
        </>
      ) : (
        <>
          <h1 className={styles.onboardTitle}>One goal.</h1>
          {/* What this screen used to say last was "you can retire it later,
              but he'll remember" — reversibility and a warning in one breath,
              on the one screen where nobody has done anything yet to be
              warned about. The reversibility is worth saying and stays; the
              threat is spent here and lands properly in the retire flow,
              where there is a record to keep. What the sentence owes instead
              is the shape of what they're agreeing to: a commitment nobody
              has priced reads as unlimited.

              It priced the daily cost and stopped there, which left the
              expensive half unpriced: what they think they are signing up to
              finish. "Pick the one that matters" is a sentence about
              choosing correctly, on the one screen where nobody can yet —
              and the freeze here is not indecision, it is a 19-year-old
              reading the box as a promise to see this through. So the
              sentence says what the server already does: the commitment is
              to TEST the problem, the first step out of IDEA is one evening
              at a desk (gates.PROOFS_REQUIRED[IDEA] is 1, and its bar is
              desk work), and an idea killed by real people reads as tested
              rather than failed. That last one is conditional on purpose:
              reads_as needs INVALIDATED_AT contact proofs before it says
              "tested → dead", so the promise is about dying in front of
              people, never about closing. */}
          <p className={styles.onboardSub}>
            Pick the problem you&apos;ll test first — not the idea you&apos;ll
            finish. Then it&apos;s one task each morning and proof of it each
            evening, about two minutes a day.
          </p>
          {/* Split rather than cut: every sentence below earned its place
              against a real failure, and none of them is gone. What changed
              is when they arrive. All five jobs used to land as one block at
              the moment of least investment — 223px and 90 words at 390×844,
              a quarter of the viewport, in front of somebody who has just
              handed over a Google account and typed nothing — which is the
              shape of a terms-and-conditions wall above the box.

              The two that stay above are the two the commit is actually a
              commitment to: test first rather than finish, and the daily
              price. The rest is what a hesitating builder goes LOOKING for,
              which is what a disclosure is for — closed it costs a line, and
              the answer is one tap from the box it is about. */}
          <details className={styles.onboardMore}>
            <summary>What you&apos;re agreeing to</summary>
            <p>
              Masterji coaches one thing at a time. The first thing he asks
              for is one evening at your desk. You can close it whenever you
              like, and an idea that dies in front of real people reads as
              tested on your record — most first ones should.
            </p>
          </details>
        </>
      )}

      <div className={styles.onboardForm}>
        <input
          ref={goalBoxRef}
          className={styles.input}
          placeholder={
            closing ? "So — what's next?" : "e.g. Tiffin-delivery app for my college"
          }
          value={goalTitle}
          maxLength={200}
          onChange={(e) => setGoalTitle(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && onCreateGoal()}
        />
        {/* Weight, never permission: `disabled` is still `busy` alone, and
            this press does the same thing at nought of four as at four of
            four. See commitIsLoud — including the row that matters most,
            which is that a spent room gets the filled button back, because by
            then the composer is gone and the closing copy points here. */}
        <button
          className={commitLoud ? styles.primaryBtn : styles.secondaryBtn}
          disabled={busy}
          onClick={onCreateGoal}
        >
          Commit
        </button>
      </div>

      {/* First run only — `closing` is set by an archive entry as well as by
          a just-retired goal, so this is off for everyone who has done this
          before. They know the shape; the examples would be clutter, and the
          screen they're on is a victory lap.

          These fill the box rather than committing: the goal has to be
          theirs, and one tap from "example" to "locked in a database
          constraint" is how you get a user coached on somebody else's idea.
          Filling it leaves the edit — and the decision — with them. */}
      {!closing && (
        <div className={styles.examples}>
          <p id="goal-examples-label" className={styles.examplesLabel}>
            Roughly this specific:
          </p>
          {/* Named by the line above rather than by three aria-labels: the
              buttons say a goal each, and what a goal is doing in a button
              is the one thing their own text can't carry. */}
          <ul className={styles.exampleList} aria-labelledby="goal-examples-label">
            {GOAL_EXAMPLES.map((example) => (
              <li key={example}>
                <button
                  type="button"
                  className={styles.example}
                  /* Spent once the goal is theirs. Filling the box would
                     throw away a sentence they typed, and it does not come
                     back: setting a controlled input's value through React
                     takes the browser's own undo stack with it, so Ctrl+Z
                     returns the example, not their words. Verified, not
                     assumed.

                     Dimmed rather than unmounted, because this column is
                     centred: dropping the block the moment they start typing
                     re-centres everything and slides the box out from under
                     the cursor they are typing into. Switching between
                     examples stays live — swapping one example for another
                     costs nothing. */
                  disabled={examplesSpent}
                  onClick={() => {
                    setGoalTitle(example);
                    // And put them in the box it filled — the same move the
                    // evening's draft button makes, for the same reason. The
                    // whole promise of an example is "now make it yours",
                    // and that is a lie if editing starts with a hunt for
                    // the caret.
                    goalBoxRef.current?.focus();
                  }}
                >
                  {example}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Said out loud, because a link the builder cannot see is a link they
          cannot decline. What carries over is what they LEARNED — the people
          they spoke to and what those people said, as facts the coach is
          handed — and nothing they earned: the new goal starts at IDEA with
          nothing banked and its first proof is owed exactly as if this were
          their first day.

          Droppable in one press. They asked for it thirty seconds ago on the
          previous screen, and by the time they have typed a title they may
          have decided this is a different problem after all. */}
      {pivotFrom !== null && closing && (
        <p className={styles.carrying}>
          Carrying what you learned on{" "}
          <strong>{closing.title}</strong> — the conversations, not the
          counts. This one still starts at IDEA.{" "}
          <button
            type="button"
            className={styles.carryingOff}
            onClick={() => setPivotFrom(null)}
          >
            start clean instead
          </button>
        </p>
      )}

      {error && <p className={styles.error}>{error}</p>}

      {/* What the room has produced FOR the box, next to the box. Both of
          these came out of the conversation and both of them are about the
          commit rather than about the talking, which is why they moved out
          of the log's column: the pile is what you pick from and the
          forecast is what picking would cost. */}

      {/* Parked candidates, and the one his tiebreak landed on. Both fill
          the commit box and neither commits — the goal-examples bargain,
          which exists because one tap from "his suggestion" to a database
          constraint is how a builder ends up coached on somebody else's
          idea. The pile is capped at three server-side; nothing here
          enforces it, and nothing here needs to. */}
      {ws && (ws.candidates.length > 0 || ws.suggestedTitle) && (
        <div className={styles.parked}>
          <p id="parked-label" className={styles.parkedLabel}>
            {ws.candidates.length >= ws.maxCandidates
              ? `Three parked — that's the lot. Pick one:`
              : `Parked (${ws.candidates.length}/${ws.maxCandidates}) — tap to put it in the box:`}
          </p>
          <ul className={styles.parkedList} aria-labelledby="parked-label">
            {ws.suggestedTitle && (
              <li key="suggested">
                <button
                  type="button"
                  className={styles.parkedPick}
                  onClick={() => {
                    setGoalTitle(ws.suggestedTitle);
                    goalBoxRef.current?.focus();
                  }}
                >
                  {ws.suggestedTitle}
                  <span className={styles.parkedPickNote}>his pick</span>
                </button>
              </li>
            )}
            {/* By position, the way the same strings are keyed where they
                are shown again after the goal closes (ClosedIdea's
                "considered"). The list is append-only and never reordered or
                filtered, so a position is a stable identity for as long as
                the row lives, and the one-liner is not: the server refuses a
                repeat park now, but rooms that took one before it did still
                hold two identical strings, and keying by the text there is
                two children with one key — a React warning, and a
                reconciler free to duplicate or drop a card. */}
            {ws.candidates.map((c, i) => (
              <li key={i}>
                <button
                  type="button"
                  className={styles.parkedItem}
                  onClick={() => {
                    setGoalTitle(c);
                    goalBoxRef.current?.focus();
                  }}
                >
                  {c}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* What this room is FOR, standing on screen the whole time it is open:
          the four things IDEA will ask for, and which of them the
          conversation has turned up. Under the cards because the pile is what
          you pick from and this is what sharpening the pick produces. Still a
          readout — every fact in it was counted by the server off what the
          coach extracted, the labels included, because bar.py owns IDEA's
          wording and the evening is judged against that same list.

          From the room's turn zero, which is the change here. It used to
          appear only once a part had landed, and the comment defending that
          was about not showing "0 of 4" to somebody who had not spoken yet.
          That concern was real and it was answered by hiding the wrong thing:
          what made the old block bad was the COUNTER — a score you are losing
          before you have said anything. Four named questions are not a score,
          they are the agenda, and a room whose agenda is invisible until you
          accidentally satisfy part of it is the room a builder spent nine of
          fifteen turns in without learning it had a shape.

          Still scoped to an opened room. The screen somebody lands on the
          moment they finish signing up is tuned against a real first
          impression (masterji.module.css says so at the top), and four
          questions about a candidate that does not exist yet are noise on it.

          It never gates, and that has NOT changed: committing at nought of
          four works exactly as it does at four of four, nothing here is
          disabled, and no server-side check was added. What changed is the
          second half of the old sentence — Commit is no longer the only
          filled control on the screen while the conversation is unfinished.
          The scaffold is the loudest thing in this column until the four are
          full, and the volume rule is commitIsLoud in lib/gate.ts, where the
          state it depends on can be stated and tested. The screen carries the
          opinion; the server and the coach still carry none. */}
      {ws && roomOpen && ws.sketch.asks.length > 0 && (
        <div className={styles.sketch} data-full={sketchFull ? "yes" : "no"}>
          <p className={styles.sketchLabel}>
            {sketchFull
              ? "All four. Your first evening's proof is already in this conversation."
              : "What IDEA will ask you for"}
          </p>
          <ul className={styles.sketchList}>
            {ws.sketch.asks.map((ask) => (
              <li
                key={ask.key}
                className={ask.have ? styles.sketchHave : styles.sketchOpen}
              >
                {/* The words carry the state, not the glyph. Two rows whose
                    text is identical in both states would be told apart only
                    by a tick, and a reader that skips decoration would hear
                    four answered questions where four are open. */}
                <span className={styles.sketchMark} aria-hidden="true">
                  {ask.have ? "✓" : "○"}
                </span>
                <span>
                  <span className={styles.sketchState}>
                    {ask.have ? "Told him: " : "Still open: "}
                  </span>
                  {ask.label}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>

      {/* --- the workshop ------------------------------------------------
          The room before the goal, and the same activity as the chat pane
          — talking to Masterji — so it is now drawn in the same language.
          Masterji has his face here, his line is unboxed behind it, the
          builder's is the filled one, the body is 15px and the box grows a
          line at a time: every one of those was inverted or absent in the
          first conversation a builder ever has with him.

          What has NOT changed is the hierarchy the room was built with. It
          is still subordinate — Send is still `secondaryBtn` against the
          one filled Commit, the room is still the way in for a builder who
          cannot fill the box rather than the point of the screen, and the
          turn meter is still on screen from turn zero. Grammar and
          hierarchy are separable; this screen was paying for the second
          with the first and getting nothing for it.

          Everything here is a control. What the room is FOR is explained in
          the tour, not in help text wedged between the buttons. */}
      <Workshop reopened={false} {...room} />

      {state.archive.length > 0 && (
        <section className={styles.archive}>
          <p className={styles.cardLabel}>Behind you</p>
          <ul className={styles.archiveList}>
            {state.archive.map((r) => (
              <li key={r.id}>
                <button
                  className={styles.archiveButton}
                  onClick={() => setViewClosed(r)}
                  title="See how this one went"
                >
                  <span className={styles.archiveTitle}>{r.title}</span>
                  <span className={CLOSED_CHIP[r.readsAs].className(styles)}>
                    {CLOSED_CHIP[r.readsAs].label}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* The tour matters most here and costs least here: this is the screen
          somebody lands on the moment they finish signing up, with nothing
          on it yet to explain itself, and this row stays quiet rather than
          becoming a full control strip.

          The language switch is the fourth thing in it, and that is a real
          charge against the sentence above — paid because the workshop this
          row sits under has been speaking whichever language it sets all
          along, with no way to say which. It goes LAST so nothing already
          here moves: sign out is deliberately leftmost (see .signOut)
          because its label grows to "sign out?" on the first press, and a
          control that shifts under the thumb mid-confirmation is the one
          thing this row must not do. If the row ever does read as clutter,
          the next place to try is the workshop head beside the turn meter —
          not a caption or a disclosure explaining what the languages are. */}
      <div className={styles.onboardFooter}>
        <SignOutButton />
        <TourLink />
        <Changelog />
        <ToneSwitch tone={state.tone} busy={busy} onSet={onSetTone} />
      </div>

      {viewClosed && (
        <ClosedIdea closed={viewClosed} onClose={() => setViewClosed(null)} />
      )}
    </main>
  );
}
