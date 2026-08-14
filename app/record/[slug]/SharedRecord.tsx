"use client";

// A closed goal, as a page you can hand to somebody: an E-Cell application, a
// placement folder, a parent. Reachable by anybody holding the link and by
// nobody else — the slug is the access control, and a wrong one is the same
// 404 as a missing one.
//
// Everything on it was computed by the server from rows the builder had to
// earn. That is the whole pitch, and it is why the page says so out loud at
// the bottom: "reached BUILD, 5 accepted proofs, 4 from real-world contact" is
// a claim a reader can audit in a public repo, which is not true of any deck.
//
// What is NOT on it: the reason they closed it, the goal's brief, any proof
// text, any check-in, the coach's words, and the builder's name. The record is
// the shape of the work rather than a diary, and prose is the one thing you
// cannot take back once a link is out.

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { getSharedRecord, type SharedRecord as Record_ } from "@/lib/coach-api";
import styles from "./record.module.css";

const VERDICT: Record<string, { label: string; note: string }> = {
  ACHIEVED: {
    label: "Achieved",
    note: "Finished, with proof on the record behind it.",
  },
  UNVERIFIED: {
    label: "Achieved · unverified",
    note: "Called finished, without the banked evidence to show it.",
  },
  // The one this page exists for. A dead idea with contact proofs behind it is
  // the only version of "it didn't work out" that reads as competence, and it
  // is not the builder's to claim — gates.reads_as computes it.
  INVALIDATED: {
    label: "Tested → dead",
    note: "Taken to real people, and they said no. That is a result.",
  },
  UNTESTED: {
    label: "Untested",
    note: "Closed before it reached anybody outside.",
  },
};

const day = (iso: string) =>
  new Date(iso).toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });

export default function SharedRecord() {
  const { slug } = useParams<{ slug: string }>();
  const [record, setRecord] = useState<Record_ | null>(null);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getSharedRecord(String(slug))
      .then((r) => !cancelled && setRecord(r))
      .catch(() => !cancelled && setMissing(true));
    return () => {
      cancelled = true;
    };
  }, [slug]);

  if (missing) {
    return (
      <main className={styles.page}>
        <p className={styles.gone}>
          No record here. The link may have been turned off — that is the
          builder&apos;s to decide, and it is meant to be reversible.
        </p>
      </main>
    );
  }
  if (!record) {
    return (
      <main className={styles.page}>
        <p className={styles.gone}>Reading the record…</p>
      </main>
    );
  }

  const verdict = VERDICT[record.readsAs] ?? VERDICT.UNTESTED;
  return (
    <main className={styles.page}>
      <p className={styles.wordmark}>मास्टरजी</p>
      <h1 className={styles.title}>{record.title}</h1>

      <p className={styles.verdict}>{verdict.label}</p>
      <p className={styles.verdictNote}>{verdict.note}</p>

      {/* The counts, and the second one is the one that means something: an
          accepted proof stamped VALIDATION or later required real-world
          contact, so "4 of 5 from talking to people" is a different claim from
          "5 things done". */}
      <ul className={styles.figures}>
        <li>
          <span className={styles.figure}>{record.phaseReached}</span>
          <span className={styles.figureLabel}>phase reached</span>
        </li>
        <li>
          <span className={styles.figure}>{record.acceptedProofs}</span>
          <span className={styles.figureLabel}>
            accepted proof{record.acceptedProofs === 1 ? "" : "s"}
          </span>
        </li>
        <li>
          <span className={styles.figure}>{record.contactProofs}</span>
          <span className={styles.figureLabel}>from real-world contact</span>
        </li>
        <li>
          <span className={styles.figure}>{record.daysActive}</span>
          <span className={styles.figureLabel}>
            day{record.daysActive === 1 ? "" : "s"} active
          </span>
        </li>
        <li>
          <span className={styles.figure}>{record.bestStreak}</span>
          <span className={styles.figureLabel}>longest run</span>
        </li>
      </ul>

      <ol className={styles.timeline}>
        <li>
          <span className={styles.when}>{day(record.startedOn)}</span>
          <span className={styles.what}>started in IDEA</span>
        </li>
        {record.timeline.map((t) => (
          <li key={`${t.toPhase}-${t.on}`}>
            <span className={styles.when}>{day(t.on)}</span>
            <span className={styles.what}>reached {t.toPhase}</span>
          </li>
        ))}
        <li>
          <span className={styles.when}>{day(record.closedOn)}</span>
          <span className={styles.what}>closed</span>
        </li>
      </ol>

      {/* Said plainly, because it is the difference between this page and every
          other page like it. The reader is being told what they can check. */}
      <p className={styles.footnote}>
        Every number here was counted by{" "}
        <a href="/" className={styles.link}>
          Masterji
        </a>{" "}
        from evidence this builder filed and had judged, one evening at a time.
        None of it is self-reported, and the gate that decided it is open
        source.
      </p>
    </main>
  );
}
