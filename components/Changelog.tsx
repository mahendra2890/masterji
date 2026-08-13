"use client";

// The product's own record: a quiet link in the header, and every active
// entry in a scrollable popup. The entries live in the database and are
// written from the admin, so announcing a change doesn't need a deploy.
//
// Rendered from the app header, the between-goals screen and the demo — the
// endpoint is public, so the same component works signed out.

import { useCallback, useEffect, useRef, useState } from "react";
import { getChangelog, type ChangelogEntry } from "@/lib/coach-api";
import { useDialogFocus } from "@/lib/dialog-focus";
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

/** How many entries the mount fetch asks for.
 *
 * Enough to fill the popup on the first screen — it caps at min(82dvh, 720px)
 * and an entry runs around 110px — so somebody who opens this reads real
 * content while the rest is still in flight, rather than a spinner. Small
 * enough that the price of the dot came down from 42KB to 3.7KB (measured at
 * 77 entries; the ratio is what matters, since the list only ever grows). */
const PREVIEW = 6;

export default function Changelog() {
  const [entries, setEntries] = useState<ChangelogEntry[] | null>(null);
  // How many exist, as the server counts them. `entries.length < total` is
  // what "we are holding the preview" means — asked rather than inferred from
  // the length matching PREVIEW, which is wrong on the day there are exactly
  // six.
  const [total, setTotal] = useState(0);
  const [failed, setFailed] = useState(false);
  // The rest didn't arrive. Distinct from `failed`, which is nothing arriving:
  // here the preview is on screen and readable, and the only thing owed is the
  // tail — so the popup says so under the entries instead of replacing them
  // with an error.
  const [tailFailed, setTailFailed] = useState(false);
  const [loadingTail, setLoadingTail] = useState(false);
  const [open, setOpen] = useState(false);
  // Read from localStorage in an effect, so the first client render matches
  // the server's (no dot) and hydration stays quiet. "" = never read.
  const [seen, setSeen] = useState<string | null>(null);
  // The full list has been asked for. Set the moment the request goes out, so
  // a preview still in flight when somebody opens the popup cannot land
  // afterwards and cut the whole list back to six under the reader.
  const asked = useRef(false);

  /** The newest few. What every mount pays, on every screen. */
  const load = useCallback(() => {
    setFailed(false);
    getChangelog(PREVIEW)
      .then(({ entries, total }) => {
        if (asked.current) return; // the whole list is on its way or here
        setEntries(entries);
        setTotal(total);
      })
      .catch(() => {
        if (!asked.current) setFailed(true);
      });
  }, []);

  /** The whole list, once somebody has actually asked to read it — which is
   * what opening the popup is.
   *
   * Replaces rather than appends: one request is one consistent snapshot, and
   * stitching a tail onto a preview taken seconds earlier can duplicate or skip
   * an entry published in between. Re-reading the 3KB is the price of that, and
   * only a reader who opened the popup ever pays it. */
  const loadAll = useCallback(() => {
    asked.current = true;
    setFailed(false);
    setTailFailed(false);
    setLoadingTail(true);
    getChangelog()
      .then(({ entries, total }) => {
        setEntries(entries);
        setTotal(total);
      })
      // Which of the two messages this becomes is decided at render, by whether
      // there is anything on screen to be a footnote to: a preview that arrived
      // gets "the older ones didn't load", an empty popup gets the whole-list
      // error and its own retry.
      .catch(() => setTailFailed(true))
      .finally(() => setLoadingTail(false));
  }, []);

  // On mount rather than on click: the dot has to know the newest date before
  // anyone opens anything, and only the newest entry can answer that — which
  // is why this asks for a handful and not for all of them.
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

  // The trigger stays mounted behind this one, so `open` is the whole of it —
  // and it is also what puts focus back on "What's new" rather than on the top
  // of a header the reader has already tabbed past.
  const dialog = useRef<HTMLDivElement>(null);
  useDialogFocus(dialog, open);

  const latest = entries?.[0]?.shippedOn ?? "";
  // ISO dates compare correctly as strings, and a browser that has never
  // read the list is behind by definition.
  const unseen = seen !== null && latest !== "" && seen < latest;

  // Everything the server has, as far as this browser knows. `entries` null is
  // the mount fetch still in flight, which is not "holding all of them".
  const haveAll = entries !== null && entries.length >= total;

  const onOpen = () => {
    setOpen(true);
    // Opening IS the ask, and it is the only request in this component anybody
    // asked for. One call covers every state the preview can have left behind —
    // it flaked, it is still in flight, it arrived with more behind it — because
    // in all three the answer a reader wants is the whole list.
    if (!haveAll) loadAll();
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
            ref={dialog}
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

            {/* Nothing on screen at all: either the mount fetch flaked and the
                open-fetch has not answered yet, or the open-fetch flaked too.
                Retrying asks for the whole list — a reader looking at this has
                the popup open, so the preview is not what they want. */}
            {failed || (tailFailed && !entries) ? (
              <p className={styles.empty}>
                Couldn&apos;t load the changelog.{" "}
                <button className={styles.retry} onClick={loadAll}>
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

            {/* Under the entries, never instead of them. The preview is real
                content and already readable, so what is outstanding is only the
                tail and this is a footnote about the tail. It names the number,
                because a wait with no size to it reads as broken. */}
            {entries !== null && entries.length > 0 && !haveAll && (
              <p className={styles.tail}>
                {loadingTail ? (
                  `Fetching the other ${total - entries.length}…`
                ) : (
                  <>
                    {total - entries.length} older{" "}
                    {total - entries.length === 1 ? "entry" : "entries"}{" "}
                    didn&apos;t load.{" "}
                    <button className={styles.retry} onClick={loadAll}>
                      Try again
                    </button>
                  </>
                )}
              </p>
            )}
          </div>
        </div>
      )}
    </>
  );
}
