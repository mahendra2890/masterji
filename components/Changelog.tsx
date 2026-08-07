"use client";

// The product's own record: a quiet link in the header, and every active
// entry in a scrollable popup. The entries live in the database and are
// written from the admin, so announcing a change doesn't need a deploy.
//
// Rendered from the app header, the between-goals screen and the demo — the
// endpoint is public, so the same component works signed out.

import { useCallback, useEffect, useState } from "react";
import { getChangelog, type ChangelogEntry } from "@/lib/coach-api";
import styles from "./changelog.module.css";

/** The newest date this browser has read. A dot nags until it catches up. */
const SEEN_KEY = "masterji.changelog.seen";

const KIND_LABEL: Record<ChangelogEntry["kind"], string> = {
  NEW: "new",
  CHANGED: "changed",
  FIXED: "fixed",
  METHOD: "method",
};

/** Parsed as UTC and rendered as UTC: shipped_on is a calendar date, and
 * letting the browser's timezone touch it slides half the world's entries a
 * day backwards. */
const formatDate = (ymd: string) =>
  new Date(`${ymd}T00:00:00Z`).toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });

export default function Changelog() {
  const [entries, setEntries] = useState<ChangelogEntry[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [open, setOpen] = useState(false);
  // Read from localStorage in an effect, so the first client render matches
  // the server's (no dot) and hydration stays quiet. "" = never read.
  const [seen, setSeen] = useState<string | null>(null);

  const load = useCallback(() => {
    setFailed(false);
    getChangelog()
      .then(setEntries)
      .catch(() => setFailed(true));
  }, []);

  // On mount rather than on click: the dot has to know the newest date
  // before anyone opens anything. It's one small unauthenticated GET.
  useEffect(() => {
    load();
    try {
      setSeen(localStorage.getItem(SEEN_KEY) ?? "");
    } catch {
      // Storage blocked (private mode, embedded webview) — no dot, and the
      // popup still works. Not worth surfacing.
      setSeen("");
    }
  }, [load]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const latest = entries?.[0]?.shippedOn ?? "";
  // ISO dates compare correctly as strings, and a browser that has never
  // read the list is behind by definition.
  const unseen = seen !== null && latest !== "" && seen < latest;

  const onOpen = () => {
    setOpen(true);
    if (failed) load(); // a flaked fetch shouldn't leave an empty popup forever
    if (latest) {
      setSeen(latest);
      try {
        localStorage.setItem(SEEN_KEY, latest);
      } catch {}
    }
  };

  return (
    <>
      <button
        className={styles.trigger}
        onClick={onOpen}
        title="What's changed in Masterji lately"
      >
        What&apos;s new
        {unseen && <span className={styles.dot} aria-hidden="true" />}
      </button>

      {open && (
        <div className={styles.overlay} onClick={() => setOpen(false)}>
          <div
            className={styles.modal}
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-label="What's changed in Masterji"
          >
            <div className={styles.modalHeader}>
              <h3>What&apos;s changed</h3>
              <button
                className={styles.modalClose}
                onClick={() => setOpen(false)}
                aria-label="Close"
              >
                ×
              </button>
            </div>

            <p className={styles.blurb}>
              Masterji demands proof of work every evening, so he keeps a
              record of his own. Newest first.
            </p>

            {failed ? (
              <p className={styles.empty}>
                Couldn&apos;t load the changelog.{" "}
                <button className={styles.retry} onClick={load}>
                  Try again
                </button>
              </p>
            ) : !entries ? (
              <p className={styles.empty}>Loading…</p>
            ) : entries.length === 0 ? (
              <p className={styles.empty}>Nothing published yet.</p>
            ) : (
              <ol className={styles.list}>
                {entries.map((e, i) => {
                  // One date heading per day: several changes a day is the
                  // normal case here.
                  const newDay =
                    i === 0 || entries[i - 1].shippedOn !== e.shippedOn;
                  return (
                    <li key={e.id} className={styles.entry}>
                      {newDay && (
                        <p className={styles.date}>{formatDate(e.shippedOn)}</p>
                      )}
                      <p className={styles.entryHead}>
                        <span className={styles[e.kind.toLowerCase()]}>
                          {KIND_LABEL[e.kind]}
                        </span>
                        <span className={styles.entryTitle}>{e.title}</span>
                      </p>
                      <p className={styles.entryBody}>{e.body}</p>
                    </li>
                  );
                })}
              </ol>
            )}
          </div>
        </div>
      )}
    </>
  );
}
