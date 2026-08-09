"use client";

// One day of the record, opened from a row in the sidebar's THE RECORD or
// from the phase drill-in. A row used to be a dead end: the declaration and
// a ✓/✗, with the proof, the screenshot and Masterji's reaction reachable
// nowhere. Everything the day holds is already in the state payload, so this
// costs no fetch.

import { useEffect } from "react";
import DayRecord, { VERDICT } from "@/components/DayRecord";
import { formatDay, type CheckIn } from "@/lib/coach-api";
import styles from "./masterji.module.css";

export default function DayDetail({
  checkin,
  onClose,
}: {
  checkin: CheckIn;
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

  return (
    <div className={`${styles.modalOverlay} ${styles.dayOverlay}`} onClick={onClose}>
      <div
        className={styles.modal}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={`${formatDay(checkin.date)} — the whole day`}
      >
        <div className={styles.modalHeader}>
          <h3>{formatDay(checkin.date)}</h3>
          <button className={styles.modalClose} onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>

        <p className={styles.modalMeta}>
          {checkin.phase && <span className={styles.metaBit}>{checkin.phase}</span>}
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
