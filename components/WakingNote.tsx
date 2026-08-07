"use client";

import { useEffect, useState } from "react";
import styles from "./waking-note.module.css";

// What a free-tier boot really costs: container start, then migrate and
// ensure_admin against a Neon compute that is also resuming, all on 0.1 CPU
// (backend/start.sh). Two minutes is the honest number. Past it the note
// stops calling the wait normal instead of promising forever.
const EXPECTED_MS = 120_000;

const mmss = (ms: number) => {
  const total = Math.floor(ms / 1000);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
};

/** The one cold-start note, shown wherever a visitor is stuck behind a
 * sleeping API: /admin/ through proxy.ts, the app itself through AuthGate.
 * It only counts — whoever renders it owns the retrying and unmounts it
 * once the API answers. `lateHint` is where a caller that has somewhere to
 * point (the admin's boot logs) says so. */
export default function WakingNote({ lateHint }: { lateHint?: React.ReactNode }) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const startedAt = Date.now();
    const tick = setInterval(() => setElapsed(Date.now() - startedAt), 1000);
    return () => clearInterval(tick);
  }, []);

  const overdue = elapsed > EXPECTED_MS;

  return (
    <section className={styles.card}>
      <p className={styles.kicker}>cold start</p>
      <h1 className={styles.title}>The server is waking up.</h1>
      <p className={styles.body}>
        Masterji&apos;s backend sleeps after 15 quiet minutes — the honest
        price of free hosting. Starting it again takes about two minutes,
        migrations and all. Leave this tab open: it goes through on its own the
        moment the server answers.
      </p>
      <div
        className={styles.bar}
        aria-hidden="true"
        style={
          {
            "--progress": `${Math.min(100, (elapsed / EXPECTED_MS) * 100)}%`,
          } as React.CSSProperties
        }
      >
        <span className={styles.fill} />
      </div>
      <p className={styles.meta}>
        {overdue ? "longer than usual —" : "waiting"} {mmss(elapsed)}
        <span className={styles.dim}> · usually through by 2:00</span>
      </p>
      {overdue && (
        <p className={styles.late} role="status">
          Still knocking every few seconds. If nothing lands, the server itself
          is unhappy{lateHint ? <> — {lateHint}</> : "."}
        </p>
      )}
    </section>
  );
}
