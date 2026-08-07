import noteStyles from "@/components/waking-note.module.css";
import styles from "./waking.module.css";
import Waking from "./Waking";

export const metadata = { title: "Waking up — Masterji" };

/** Shown in place of Render's boot-log page while the free instance starts
 * (see proxy.ts). Reached by rewrite, so the browser's URL is still the
 * admin path the visitor asked for. */
export default async function WakingPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string }>;
}) {
  const { next } = await searchParams;

  // This value is handed to the browser as a redirect target, so only take
  // it when it's the admin path we put there: no protocol-relative "//host"
  // slipping through as an open redirect, and no "/admin/../elsewhere",
  // which the browser would quietly resolve back out of /admin/.
  const wanted = next && /^\/admin(\/|$)/.test(next) && !next.includes("..");
  const dest = wanted ? next : "/admin/";
  const logs = `${dest}${dest.includes("?") ? "&" : "?"}boot=logs`;

  return (
    <main className={noteStyles.screen}>
      <a className={styles.flag} href={logs}>
        show the server&apos;s own boot logs →
      </a>
      <Waking dest={dest} />
    </main>
  );
}
