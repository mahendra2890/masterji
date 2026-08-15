"use client";

// The room, drawn once for both of the screens that can hold one — the
// pre-goal room on the onboarding screen, and this goal's one reopening on the
// dashboard.

import type { RefObject } from "react";
import { isSendKey } from "@/lib/send-key";
import type { Workshop as WorkshopRoom } from "@/lib/coach-api";
import styles from "./masterji.module.css";

/** The room, drawn once for both of the screens that can hold one.
 *
 * A module-level component, and it has to stay one. Declared inside
 * `Masterji()` — as a nested component, or as the function returning JSX this
 * used to be — its type would be new on every render, so React would remount
 * the composer and take the caret out of it mid-sentence. That hazard is real
 * and this is what holds it off: a component whose type is fixed at module
 * load re-renders its composer, never remounts it, and the refs come in as
 * props rather than being closed over.
 *
 * What differs between the two rooms is copy and one block — the reopened room
 * has no openers, because "start with:" is for a builder who has nothing, and
 * this one has a goal, a phase and three weeks of record. What does not differ
 * is everything the room IS: the meter, the transcript, the composer, and that
 * nothing in it banks.
 *
 * The prop list is wide because it is the honest measure of how much this
 * block was reaching into its parent, not a reason to put it back. */
export default function Workshop({
  reopened,
  ws,
  roomTurnsLeft,
  workshopTurns,
  workshopOpeners,
  wsDraft,
  wsStreaming,
  wsPending,
  wsError,
  wsLogRef,
  wsBoxRef,
  attachWsComposer,
  setWsDraft,
  sendWorkshop,
}: {
  reopened: boolean;
  ws: WorkshopRoom | null;
  roomTurnsLeft: number;
  workshopTurns: number;
  workshopOpeners: string[];
  wsDraft: string;
  wsStreaming: string | null;
  wsPending: string | null;
  wsError: string;
  wsLogRef: RefObject<HTMLDivElement | null>;
  /** Read here only, to put the caret in the box an opener just filled. It is
   * written by attachWsComposer below, which is the ref callback the textarea
   * actually carries. */
  wsBoxRef: RefObject<HTMLTextAreaElement | null>;
  attachWsComposer: (el: HTMLTextAreaElement | null) => void;
  setWsDraft: (v: string) => void;
  sendWorkshop: () => void;
}) {
  return (
    <section className={styles.workshop}>
      <div className={styles.workshopHead}>
        <p className={styles.workshopTitle}>
          {roomTurnsLeft === 0 && ws
            ? reopened
              ? "Room closed."
              : "Workshop closed."
            : reopened
              ? "Still the right idea? Say it out loud."
              : "Not sure yet? Think it through with him."}
        </p>
        {/* The meter is the mechanism, so it is on screen BEFORE the first
            turn, not from the second: a room whose hard end only announces
            itself once you are near it is a trapdoor. Both numbers are the
            server's — turnsLeft is computed there so this and the refusal can
            never disagree, and the budget is sent even with no room open
            precisely so this line can exist at rest. The reopened room's
            budget is smaller and the server says which it is sending. */}
        {workshopTurns > 0 && (
          <p className={styles.workshopTurns}>
            {roomTurnsLeft} of{" "}
            {ws ? ws.turnsTotal : workshopTurns} turns left
          </p>
        )}
      </div>

      {(ws?.messages.length || wsPending !== null) && (
        <div className={styles.workshopLog} ref={wsLogRef}>
          {ws?.messages.map((m) =>
            /* A turn that never landed, in the log's one shape that belongs
               to neither speaker — the same dashed pill the chat uses,
               because it is the same event: the app saying a turn broke. It
               used to be drawn as something Masterji said. */
            m.role === "SYSTEM" ? (
              <div key={m.id} data-turn className={styles.systemMsg}>
                <p className={styles.systemText}>{m.content}</p>
              </div>
            ) : (
              <div
                key={m.id}
                data-turn
                className={m.role === "USER" ? styles.userMsg : styles.coachMsg}
              >
                {m.role === "COACH" && <span className={styles.avatar}>म</span>}
                <p className={styles.msgBody}>{m.content}</p>
              </div>
            )
          )}
          {wsPending !== null && (
            <div data-turn className={styles.userMsg}>
              <p className={styles.msgBody}>{wsPending}</p>
            </div>
          )}
          {wsStreaming !== null && (
            <div data-turn className={styles.coachMsg}>
              <span className={styles.avatar}>म</span>
              <p className={styles.msgBody}>
                {wsStreaming || <span className={styles.thinking}>…</span>}
              </p>
            </div>
          )}
        </div>
      )}

      {/* Openers, while the room is still silent. Same bargain as the phase
          openers in chat: tapping fills the box and leaves the sending — and
          the editing — with the builder. Tapping the first one is also how the
          coach learns they arrived empty-handed, which is the one case his
          week-walk is the right opening move for.

          Not in the reopened room. Its builder is not short of a first
          sentence — they came in with one, and it is the whole reason the
          room exists. */}
      {!reopened &&
        !ws?.messages.length &&
        wsPending === null &&
        workshopOpeners.length > 0 && (
          <div className={styles.openers}>
            <p id="ws-openers-label" className={styles.openersLabel}>
              Start with:
            </p>
            <ul className={styles.openerList} aria-labelledby="ws-openers-label">
              {workshopOpeners.map((opener) => (
                <li key={opener}>
                  <button
                    type="button"
                    className={styles.opener}
                    onClick={() => {
                      setWsDraft(opener);
                      wsBoxRef.current?.focus();
                    }}
                  >
                    {opener}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

      {wsError && <p className={styles.error}>{wsError}</p>}

      {/* No composer once the turns are gone. The refusal is already on screen
          above as the coach's own words, and leaving a box there that only ever
          answers 429 is the product pretending a door is open. */}
      {/* The {" "} in both closed-door sentences is load-bearing and must not be
          reformatted away — see the same note in Landing.tsx and Tour.tsx.
          Written as `{turns} turns, done.` it shipped as "15turns, done." for
          as long as the room has existed: the text node after the expression
          wraps to the next source line, and the build drops the space at the
          front of it. The one sentence that has to send a builder somewhere,
          with a typo in its first word. */}
      {ws && roomTurnsLeft === 0 ? (
        reopened ? (
          <p className={styles.workshopSpent}>
            {workshopTurns}{" "}
            turns, and this room opens once per goal. Nothing in here touched
            your record. Finish the bar in front of you, sharpen the wording, or
            close it today — yours to pick.
          </p>
        ) : (
          <p className={styles.workshopSpent}>
            {workshopTurns}{" "}
            turns, done. You don&apos;t need a better idea — you need one you
            can test. Put it in the box above.
          </p>
        )
      ) : (
        /* The chat's composer band, not a second one. Two fixed rows with
           `resize: none` was the room telling a builder their answer had a size
           before they had said anything — in the one conversation where the
           useful answer is long. It grows a line at a time now, up to the same
           cap, through the same fitComposer.

           Send stays `secondaryBtn`. That is the safeguard on all of this: the
           room may speak the chat's language, but the one filled control on
           whichever screen it is sitting on is not this. */
        <div className={styles.composer}>
          <div className={styles.composerRow}>
            <textarea
              ref={attachWsComposer}
              className={styles.composerInput}
              placeholder={
                reopened
                  ? "I'm not sure this is worth it any more…"
                  : "I don't know what to build yet…"
              }
              value={wsDraft}
              /* The resting height, not the height — see the same note on the
                 chat composer. */
              rows={1}
              maxLength={2000}
              disabled={wsStreaming !== null}
              onChange={(e) => setWsDraft(e.target.value)}
              onKeyDown={(e) => {
                if (isSendKey(e)) {
                  e.preventDefault();
                  sendWorkshop();
                }
              }}
            />
            <button
              type="button"
              className={styles.secondaryBtn}
              disabled={wsStreaming !== null || wsDraft.trim() === ""}
              onClick={() => sendWorkshop()}
            >
              Send
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
