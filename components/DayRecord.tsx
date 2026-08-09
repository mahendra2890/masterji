import FailedTries from "@/components/FailedTries";
import { formatDay, type CheckIn } from "@/lib/coach-api";
import styles from "@/app/masterji.module.css";

/** One day of the record, in full: what was claimed, what Masterji made of
 * it, what was shown, and how it landed.
 *
 * A day is a block, never a one-line row — the proof IS the record, so it
 * can't live behind an ellipsis. Shared by the closed-idea drill-in and the
 * tap-through from the sidebar record, because two copies of "what a day
 * looks like" is exactly the kind of thing that drifts.
 */

/** A day's verdict, spelled out. The compact ✓/✗ works in the sidebar where
 * space is tight; here it would just make the reader decode a glyph. */
const VERDICT: Record<
  CheckIn["proofStatus"],
  { label: string; className: (s: Record<string, string>) => string }
> = {
  ACCEPTED: { label: "accepted", className: (s) => s.chipGood },
  PUSHED_BACK: { label: "pushed back", className: (s) => s.chipBad },
  NONE: { label: "no proof", className: (s) => s.chipNone },
  // Says what happened rather than what was decided — nothing was. Not
  // "pending", which promises somebody is looking at it right now; the reading
  // happens when the builder files it again.
  UNJUDGED: { label: "not read yet", className: (s) => s.chipNone },
};

export default function DayRecord({
  checkin: c,
  /** The date line is the heading of a standalone day view, so the drill-in
   * puts it in the modal header instead of repeating it here. */
  showHead = true,
}: {
  checkin: CheckIn;
  showHead?: boolean;
}) {
  return (
    <>
      {showHead && (
        <p className={styles.dayHead}>
          <span className={styles.dayDate}>{formatDay(c.date)}</span>
          {c.phase && <span className={styles.dayPhase}>{c.phase}</span>}
          <span className={VERDICT[c.proofStatus].className(styles)}>
            {VERDICT[c.proofStatus].label}
          </span>
        </p>
      )}

      {c.amDeclaration && (
        <p className={styles.dayLine}>
          <span className={styles.dayWho}>Declared</span>
          <span className={styles.dayBody}>{c.amDeclaration}</span>
        </p>
      )}

      {/* Masterji's read of the morning task, kept next to the task rather
          than pooled with his verdict on the proof — they were said at
          opposite ends of the day and about different things. */}
      {c.declarationReaction && (
        <p className={styles.dayLine}>
          <span className={styles.dayWho}>
            {c.declarationFit === "OFF_PHASE" ? "Off-phase" : "Note"}
          </span>
          <span className={`${styles.dayBody} ${styles.dayCoach}`}>
            {c.declarationReaction}
          </span>
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
              presigned URL, re-signed on every read; no static host for
              next/image to optimise against. */}
          <img
            className={styles.dayImage}
            src={c.proofImageUrl}
            alt="The screenshot submitted as proof that day"
          />
        </p>
      )}

      <FailedTries attempts={c.attempts} />

      {c.coachReaction && (
        <p className={styles.dayLine}>
          <span className={styles.dayWho}>Masterji</span>
          <span className={`${styles.dayBody} ${styles.dayCoach}`}>
            {c.coachReaction}
          </span>
        </p>
      )}
    </>
  );
}

export { VERDICT };
