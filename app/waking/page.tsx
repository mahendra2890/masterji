import noteStyles from "@/components/waking-note.module.css";
import styles from "./waking.module.css";
import Waking from "./Waking";
import { resolveWakingTargets } from "./dest";

export const metadata = { title: "Waking up — Masterji" };

/** Shown while the API is starting from cold (see proxy.ts). Reached by
 * rewrite, so the browser's URL is still the path the visitor asked for —
 * /admin, or the Google sign-in link.
 *
 * The "boot logs" flag below is a leftover of Render, where the thing this
 * page replaced was Render's own log reel and linking to it was a real
 * escape hatch. On Cloud Run there is no such page: ?boot=logs now just skips
 * this note and leaves the visitor watching a blank tab for the same wait.
 * It wants removing along with `logs` in dest.ts — see #280. */
export default async function WakingPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string }>;
}) {
  const { next } = await searchParams;

  // ?next= is attacker-controllable and dest is handed to the browser as a
  // redirect target, so the rule for reading it lives in dest.ts with the
  // tests that pin it.
  const { dest, logs } = resolveWakingTargets(next);

  return (
    <main className={noteStyles.screen}>
      <a className={styles.flag} href={logs}>
        show the server&apos;s own boot logs →
      </a>
      <Waking dest={dest} />
    </main>
  );
}
