"use client";

// One day of the record, opened from a row in the sidebar's THE RECORD or
// from the phase drill-in. A row used to be a dead end: the declaration and
// a ✓/✗, with the proof, the screenshot and Masterji's reaction reachable
// nowhere. Everything the day holds is already in the state payload, so this
// costs no fetch.

import { useEffect, useRef } from "react";
import DayRecord, { VERDICT } from "@/components/DayRecord";
import { formatDay, type CheckIn } from "@/lib/coach-api";
import { useDialogFocus } from "@/lib/dialog-focus";
import { ordinalLabel } from "@/lib/record";
import styles from "./masterji.module.css";

export default function DayDetail({
  checkin,
  cycle,
  onClose,
}: {
  checkin: CheckIn;
  /** Which declare→prove cycle of its own day this is. The heading is the
   * date, and on a day that was run twice the date does not identify which of
   * the two was opened — the row it was opened from says so, and the panel
   * that replaces the screen has to keep saying it. */
  cycle: number;
  onClose: () => void;
}) {
  // Escape closes. This can open ON TOP of the phase drill-in, so without a
  // key handler the only way back is a click on the sliver of overlay not
  // covered by the modal underneath.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Always the top panel when it is open — nothing in the app layers over a
  // day — so it never stands down. Mounting IS opening here, which is what
  // makes `open` a constant.
  const dialog = useRef<HTMLDivElement>(null);
  useDialogFocus(dialog, true);

  return (
    <div className={`${styles.modalOverlay} ${styles.dayOverlay}`} onClick={onClose}>
      <div
        ref={dialog}
        className={styles.modal}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={
          // "the whole day" is only true of a day that ran once. On a day with
          // repeats this panel is one of them, and the label is the only thing
          // a screen reader gets — the marker below it is a visual column.
          cycle > 1
            ? `${formatDay(checkin.date)} — the ${ordinalLabel(cycle)} cycle of this day`
            : `${formatDay(checkin.date)} — the whole day`
        }
      >
        <div className={styles.modalHeader}>
          <h3>{formatDay(checkin.date)}</h3>
          <button className={styles.modalClose} onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>

        <p className={styles.modalMeta}>
          {checkin.phase && <span className={styles.metaBit}>{checkin.phase}</span>}
          {cycle > 1 && (
            <span className={styles.metaBit}>{ordinalLabel(cycle)} cycle</span>
          )}
          <span className={`${styles.metaBit} ${VERDICT[checkin.proofStatus].className(styles)}`}>
            {VERDICT[checkin.proofStatus].label}
          </span>
        </p>

        {/* A day with a task and nothing else is a real state, not an error:
            it's a declaration whose evening never came. Say so rather than
            opening an empty panel. */}
        {!checkin.amDeclaration && !checkin.pmProofText ? (
          <p className={styles.modalEmpty}>Nothing was recorded on this day.</p>
        ) : (
          <DayRecord checkin={checkin} showHead={false} />
        )}

        {checkin.amDeclaration && !checkin.pmProofText && (
          <p className={styles.modalEmpty}>No proof was ever submitted for this one.</p>
        )}
      </div>
    </div>
  );
}
