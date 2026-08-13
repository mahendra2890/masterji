"use client";

// The full story of a closed idea. Rendered from both the dashboard and the
// between-goals screen — the record is no use if it's only reachable from one
// of them. The day-by-day check-ins are fetched on open rather than shipped
// with every dashboard payload.

import { useEffect, useRef, useState } from "react";
import { getGoalHistory, type GoalHistory, type Retirement } from "@/lib/coach-api";
import DayRecord from "@/components/DayRecord";
import { useDialogFocus } from "@/lib/dialog-focus";
import styles from "./masterji.module.css";

const formatDate = (iso: string) =>
  new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short" });

export default function ClosedIdea({
  closed,
  onClose,
}: {
  closed: Retirement;
  onClose: () => void;
}) {
  const [history, setHistory] = useState<GoalHistory | null>(null);
  const [failed, setFailed] = useState(false);

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
          <ol className={styles.dayList}>
            {history.checkins.map((c) => (
              <li key={c.id} className={styles.day}>
                <DayRecord checkin={c} />
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}
