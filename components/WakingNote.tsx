"use client";

import { useEffect, useState } from "react";
import styles from "./waking-note.module.css";

// What a wake really costs now: a container start on a full vCPU, and nothing
// else. `MIGRATE_ON_BOOT=0` on Cloud Run, so unlike the Render deployment this
// replaced, the first request no longer waits on `migrate` and never touches
// the database (backend/start.sh, DEPLOY-cloudrun.md §5).
//
// Measured against the live service, not derived from a local container: wait
// for a 16-minute gap in the request log, then one request. 23.9s cold, 0.59s
// warm immediately after — a 40x gap, which is what proves the instance had
// really gone. Thirty is drawn a little above the measurement rather than on
// it, so an ordinary slow wake does not trip "longer than usual". Past it the
// note stops calling the wait normal instead of promising forever.
//
// Re-measure this against the deployment before changing it. The number that
// used to be here was two minutes, and it was right about Render.
const EXPECTED_MS = 30_000;

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
        Masterji&apos;s backend sleeps when nobody has needed it for a while —
        the honest price of free hosting. Starting it again takes about half a
        minute. Leave this tab open: it goes through on its own the moment the
        server answers.
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
        <span className={styles.dim}> · usually through by 0:30</span>
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
