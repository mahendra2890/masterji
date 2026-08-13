import noteStyles from "@/components/waking-note.module.css";
import styles from "./waking.module.css";
import Waking from "./Waking";
import { resolveWakingTargets } from "./dest";

export const metadata = { title: "Waking up — Masterji" };

/** Shown in place of Render's boot-log page while the free instance starts
 * (see proxy.ts). Reached by rewrite, so the browser's URL is still the path
 * the visitor asked for — /admin, or the Google sign-in link. */
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
