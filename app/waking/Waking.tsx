"use client";

import { useEffect, useState } from "react";
import styles from "./waking.module.css";

// What a free-tier boot really costs: container start, then migrate and
// ensure_admin against a Neon compute that is also resuming, all on 0.1 CPU
// (backend/start.sh). Two minutes is the honest number. Past it, the page
// stops calling the wait normal instead of promising forever.
const EXPECTED_MS = 120_000;
const POLL_EVERY_MS = 3000;

const mmss = (ms: number) => {
  const total = Math.floor(ms / 1000);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
};

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** The same test proxy.ts runs, from the browser: the health payload from
 * Django, not Render's holding page dressed as a 200. */
async function apiIsAwake(): Promise<boolean> {
  try {
    const res = await fetch("/api/health/", {
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    });
    return res.ok && (await res.text()).includes('"ok"');
  } catch {
    return false;
  }
}

export default function Waking({ dest }: { dest: string }) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const startedAt = Date.now();
    const tick = setInterval(() => setElapsed(Date.now() - startedAt), 1000);
    let stopped = false;

    (async () => {
      while (!stopped) {
        await wait(POLL_EVERY_MS);
        if (stopped) return;
        // Twice in a row before handing over: proxy.ts probes again when the
        // visitor lands, and one lucky answer would bounce them back here
        // with the clock reset to zero.
        if ((await apiIsAwake()) && (await apiIsAwake())) {
          // A real navigation, not a router push — the destination is
          // Django's, proxied by the rewrites, not a route this app owns.
          window.location.replace(dest);
          return;
        }
      }
    })();

    return () => {
      stopped = true;
      clearInterval(tick);
    };
  }, [dest]);

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
        style={{ "--progress": `${Math.min(100, (elapsed / EXPECTED_MS) * 100)}%` } as React.CSSProperties}
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
          is unhappy — the boot logs above are where that shows up.
        </p>
      )}
    </section>
  );
}
