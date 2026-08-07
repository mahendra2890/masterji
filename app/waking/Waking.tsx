"use client";

import { useEffect } from "react";
import WakingNote from "@/components/WakingNote";

const POLL_EVERY_MS = 3000;

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
  useEffect(() => {
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
    };
  }, [dest]);

  return <WakingNote lateHint="the boot logs above are where that shows up." />;
}
