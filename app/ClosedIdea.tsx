"use client";

// The full story of a closed idea. Rendered from both the dashboard and the
// between-goals screen — the record is no use if it's only reachable from one
// of them. The day-by-day check-ins are fetched on open rather than shipped
// with every dashboard payload.

import { useEffect, useState } from "react";
import {
  getGoalHistory,
  type CheckIn,
  type GoalHistory,
  type Retirement,
} from "@/lib/coach-api";
import styles from "./masterji.module.css";

const formatDate = (iso: string) =>
  new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short" });

/** A day's verdict, spelled out. The compact ✓/✗ works in the sidebar where
 * space is tight; in the record it just makes the reader decode a glyph. */
const VERDICT: Record<
  CheckIn["proofStatus"],
  { label: string; className: (s: Record<string, string>) => string }
> = {
  ACCEPTED: { label: "accepted", className: (s) => s.chipGood },
  PUSHED_BACK: { label: "pushed back", className: (s) => s.chipBad },
  NONE: { label: "no proof", className: (s) => s.chipNone },
};

export default function ClosedIdea({
  closed,
  onClose,
}: {
  closed: Retirement;
  onClose: () => void;
}) {
  const [history, setHistory] = useState<GoalHistory | null>(null);
  const [failed, setFailed] = useState(false);

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

  return (
    <div className={styles.modalOverlay} onClick={onClose}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
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
                <p className={styles.dayHead}>
                  <span className={styles.dayDate}>{c.date}</span>
                  {c.phase && <span className={styles.dayPhase}>{c.phase}</span>}
                  <span className={VERDICT[c.proofStatus].className(styles)}>
                    {VERDICT[c.proofStatus].label}
                  </span>
                </p>

                {c.amDeclaration && (
                  <p className={styles.dayLine}>
                    <span className={styles.dayWho}>Declared</span>
                    <span className={styles.dayBody}>{c.amDeclaration}</span>
                  </p>
                )}

                {c.pmProofText && (
                  <p className={styles.dayLine}>
                    <span className={styles.dayWho}>Proof</span>
                    <span className={styles.dayBody}>{c.pmProofText}</span>
                  </p>
                )}

                {c.proofUrl && (
                  <p className={styles.dayLine}>
                    <span className={styles.dayWho}>Link</span>
                    <a
                      className={styles.dayBody}
                      href={c.proofUrl}
                      target="_blank"
                      rel="noreferrer noopener"
                    >
                      {c.proofUrl}
                    </a>
                  </p>
                )}

                {c.proofImageUrl && (
                  <p className={styles.dayLine}>
                    <span className={styles.dayWho}>Shot</span>
                    {/* eslint-disable-next-line @next/next/no-img-element --
                        presigned URL, re-signed on every read; no static host
                        for next/image to optimise against. */}
                    <img
                      className={styles.dayImage}
                      src={c.proofImageUrl}
                      alt="The screenshot submitted as proof that day"
                    />
                  </p>
                )}

                {c.coachReaction && (
                  <p className={styles.dayLine}>
                    <span className={styles.dayWho}>Masterji</span>
                    <span className={`${styles.dayBody} ${styles.dayCoach}`}>
                      {c.coachReaction}
                    </span>
                  </p>
                )}
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}
