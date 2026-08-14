"use client";

// The way out, with the record on the way past it.
//
// Two presses, the same shape as SignOutButton — but the second press here is
// inside a panel rather than on the strip, because the two actions are not
// peers. Signing out costs a round trip through Google; this costs the diary.
// So the strip carries a word, and everything that makes the decision real —
// what goes, what it cannot be undone by, and the record offered before the
// button — lives in the panel it opens.
//
// The export is the point of the panel, not a courtesy in it. A product whose
// whole argument is that the record is worth having cannot let somebody delete
// theirs without putting it in front of them first, and the download is per
// goal because that is what the export endpoint is — so every goal the screen
// knows about gets its own line.

import { useEffect, useRef, useState } from "react";
import { deleteAccount } from "@/lib/auth-client";
import { useDialogFocus } from "@/lib/dialog-focus";
import TakeTheRecord from "@/components/TakeTheRecord";
import styles from "@/app/masterji.module.css";

export type ExportableGoal = { id: number; title: string };

export default function DeleteAccount({ goals }: { goals: ExportableGoal[] }) {
  const [open, setOpen] = useState(false);
  const [asking, setAsking] = useState(false);
  const [failed, setFailed] = useState(false);
  const [working, setWorking] = useState(false);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const dialog = useRef<HTMLDivElement>(null);
  useDialogFocus(dialog, open);

  async function erase() {
    setWorking(true);
    setFailed(false);
    try {
      await deleteAccount();
      // Not a refetch: there is nothing left to fetch. The landing page is
      // where signing out lands too, and for the same reason — answering
      // "I'm done" with a Google button reads as "sign in again".
      window.location.href = "/";
    } catch {
      // Said out loud. A failure reported as success here means somebody
      // walks away believing their diary is gone.
      setFailed(true);
      setWorking(false);
      setAsking(false);
    }
  }

  return (
    <>
      <button
        className={styles.linkBtn}
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
      >
        delete account
      </button>

      {open && (
        <div className={styles.modalOverlay} onClick={() => setOpen(false)}>
          <div
            ref={dialog}
            className={styles.modal}
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-label="Delete your account"
          >
            <h3>Delete your account</h3>
            <p className={styles.closedReason}>
              Every goal, every morning you declared and every evening you
              proved, the whole conversation with Masterji, and the account
              itself. It does not come back, and signing in again with the same
              Google account starts you at zero rather than finding any of it.
            </p>

            {goals.length > 0 && (
              <>
                <p className={styles.closedLabel}>Take the record first</p>
                <ul className={styles.exitRecords}>
                  {goals.map((g) => (
                    <li key={g.id}>
                      <TakeTheRecord goalId={g.id} label={g.title} />
                    </li>
                  ))}
                </ul>
              </>
            )}

            {failed && (
              <p className={styles.error}>
                That didn&apos;t go through — nothing has been deleted. Try
                again, or close this and come back.
              </p>
            )}

            <div className={styles.exitRow}>
              <button
                className={styles.linkBtn}
                onClick={() => setOpen(false)}
                disabled={working}
              >
                keep my account
              </button>
              <button
                className={styles.dangerBtn}
                disabled={working}
                onBlur={() => setAsking(false)}
                onClick={() => (asking ? erase() : setAsking(true))}
              >
                {working
                  ? "Deleting…"
                  : asking
                    ? "Press again to delete everything"
                    : "Delete everything"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
