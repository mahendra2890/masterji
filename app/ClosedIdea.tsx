"use client";

// The full story of a closed idea. Rendered from both the dashboard and the
// between-goals screen — the record is no use if it's only reachable from one
// of them. The day-by-day check-ins are fetched on open rather than shipped
// with every dashboard payload.

import { useEffect, useRef, useState } from "react";
import {
  getGoalHistory,
  shareRecord,
  type GoalHistory,
  type Retirement,
} from "@/lib/coach-api";
import DayRecord from "@/components/DayRecord";
import TakeTheRecord from "@/components/TakeTheRecord";
import { useDialogFocus } from "@/lib/dialog-focus";
import styles from "./masterji.module.css";

const formatDate = (iso: string) =>
  new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short" });

/** Built from the browser's own origin rather than from anything the server
 * sends: this app is served from one domain and the record page is a route on
 * it, so the only place the URL can come from without a second config value
 * to keep in sync is here. */
const shareUrl = (slug: string) =>
  `${typeof window === "undefined" ? "" : window.location.origin}/record/${slug}/`;

export default function ClosedIdea({
  closed,
  onClose,
}: {
  closed: Retirement;
  onClose: () => void;
}) {
  const [history, setHistory] = useState<GoalHistory | null>(null);
  const [failed, setFailed] = useState(false);
  // The public link, and whether the switch is mid-flight. Held here rather
  // than refetched from the archive because this panel is the only place it is
  // read — the dashboard has no business knowing which records are shared.
  const [slug, setSlug] = useState<string | null>(closed.shareSlug);
  const [sharing, setSharing] = useState(false);
  const [shareFailed, setShareFailed] = useState(false);

  const setShared = async (on: boolean) => {
    setSharing(true);
    setShareFailed(false);
    try {
      setSlug(await shareRecord(closed.id, on));
    } catch {
      setShareFailed(true);
    } finally {
      setSharing(false);
    }
  };

  // Escape closes, the same as every other panel in the app. This one is
  // opened from the between-goals screen as well as the dashboard, and there
  // the × is the only other way out — there is no page behind it to click.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    let cancelled = false;
    setHistory(null);
    setFailed(false);
    getGoalHistory(closed.goalId)
      .then((h) => !cancelled && setHistory(h))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [closed.goalId]);

  // The one panel that can open with nothing behind it — the between-goals
  // screen has no dashboard to fall back to — which makes the way in and the
  // way out by keyboard the only ones there are.
  const dialog = useRef<HTMLDivElement>(null);
  useDialogFocus(dialog, true);

  return (
    <div className={styles.modalOverlay} onClick={onClose}>
      <div
        ref={dialog}
        className={styles.modal}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={`${closed.title} — how this one went`}
      >
        <div className={styles.modalHeader}>
          <h3>{closed.title}</h3>
          <button className={styles.modalClose} onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>

        {/* Each fact in its own non-breaking chunk, so a narrow modal wraps
            between them instead of orphaning a number onto its own line. */}
        <p className={styles.modalMeta}>
          <span className={styles.metaBit}>
            {closed.outcome === "COMPLETED" ? "Achieved" : "Dropped"}{" "}
            {formatDate(closed.createdAt)}
          </span>
          <span className={styles.metaBit}>reached {closed.phaseReached}</span>
          <span className={styles.metaBit}>
            {closed.acceptedProofs} proof{closed.acceptedProofs === 1 ? "" : "s"} banked
            {/* The narrower count only earns a mention when it changes the
                reading — otherwise it reads as a scolding footnote. */}
            {closed.contactProofs > 0 &&
              closed.contactProofs !== closed.acceptedProofs &&
              ` (${closed.contactProofs} from contact)`}
          </span>
          <span className={styles.metaBit}>
            {closed.daysActive} day{closed.daysActive === 1 ? "" : "s"} active
          </span>
          <span className={styles.metaBit}>best streak {closed.bestStreak}</span>
        </p>

        {/* Offered here, at the top, rather than under the day list: this is
            the screen where a closed idea stops being something the builder
            uses and starts being something they show someone. */}
        <TakeTheRecord goalId={closed.goalId} />

        {/* And the other half of "show someone": a link, for the times the
            person asking cannot be handed a file — an E-Cell form, a message
            to a parent, a line in a placement folder.

            Off until pressed, and the page it opens carries computed facts
            only: the verdict, the counts, the timeline. Not the sentence
            below this one, not a proof, not their name. Prose is the thing you
            cannot take back once a link is out.

            Turning it off and on again mints a different link on purpose. A
            switch that resurrects the same URL only ever paused it. */}
        <div className={styles.share}>
          {slug ? (
            <>
              <p className={styles.shareLabel}>
                Anyone with this link can read the numbers. Not what you wrote.
              </p>
              <div className={styles.shareRow}>
                <input
                  className={styles.shareLink}
                  readOnly
                  value={shareUrl(slug)}
                  onFocus={(e) => e.currentTarget.select()}
                  aria-label="Public link to this record"
                />
                <button
                  type="button"
                  className={styles.secondaryBtn}
                  disabled={sharing}
                  onClick={() => void setShared(false)}
                >
                  Turn off
                </button>
              </div>
            </>
          ) : (
            <button
              type="button"
              className={styles.shareBtn}
              disabled={sharing}
              onClick={() => void setShared(true)}
            >
              Get a link to this record
            </button>
          )}
          {shareFailed && (
            <p className={styles.shareLabel}>
              That didn&apos;t go through. Try it again in a moment.
            </p>
          )}
        </div>

        <p className={styles.closedLabel}>What you said</p>
        <p className={styles.closedReason}>{closed.reason}</p>

        {closed.coachReaction && (
          <>
            <p className={styles.closedLabel}>What Masterji said</p>
            <div className={styles.coachMsg}>
              <span className={styles.avatar}>म</span>
              <p className={styles.msgBody}>{closed.coachReaction}</p>
            </div>
          </>
        )}

        {/* The other one-liners from the room this idea came out of. They used
            to die with the workshop, which meant the builder whose idea just
            ended had to go back to an empty room — the pivot arriving with no
            memory of the thinking that produced it. Shown here rather than as
            a control: nothing here starts a goal, and the box on the screen
            behind this panel is where that happens. */}
        {history && history.goal.considered.length > 0 && (
          <>
            <p className={styles.closedLabel}>What else was on the table</p>
            <ul className={styles.consideredList}>
              {history.goal.considered.map((one, i) => (
                <li key={i}>{one}</li>
              ))}
            </ul>
          </>
        )}

        <p className={styles.closedLabel}>Every day of it</p>
        {failed ? (
          <p className={styles.modalEmpty}>Couldn&apos;t load the daily record.</p>
        ) : !history ? (
          <p className={styles.modalEmpty}>Loading…</p>
        ) : history.checkins.length === 0 ? (
          <p className={styles.modalEmpty}>No check-ins were ever logged.</p>
        ) : (
          /* One block per day, not a one-line row: the proof IS the record,
             so it can't live in a hover tooltip or behind an ellipsis. */
          <>
            {/* Said out loud rather than left as a short list, the same rule
                the live record card follows. The history is fetched a page at
                a time; a walk that gave up partway shows the days it got, and
                a panel headed "Every day of it" that is quietly missing some
                is the one thing this record must never be. */}
            {!history.complete && (
              <p className={styles.modalEmpty}>
                Couldn&apos;t load the earlier days — showing the{" "}
                {history.checkins.length} most recent of {history.checkinsTotal}.
              </p>
            )}
            <ol className={styles.dayList}>
              {history.checkins.map((c) => (
                <li key={c.id} className={styles.day}>
                  <DayRecord checkin={c} />
                </li>
              ))}
            </ol>
          </>
        )}
      </div>
    </div>
  );
}
