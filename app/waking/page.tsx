import noteStyles from "@/components/waking-note.module.css";
import styles from "./waking.module.css";
import Waking from "./Waking";

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

  // This value is handed to the browser as a redirect target, so only take it
  // when it's one of the two paths proxy.ts puts there — /admin, or the Google
  // sign-in link. Everything else falls back: no protocol-relative "//host"
  // slipping through as an open redirect, and no "/admin/../elsewhere", which
  // the browser would quietly resolve back out of /admin/.
  //
  // The "?" in the alternation is what lets the sign-in path through with its
  // own query attached — it arrives as /api/auth/google/login/?next=%2F, the
  // whole thing round-tripped through this page's ?next=.
  const wanted =
    next &&
    /^\/(admin|api\/auth\/google\/login)(\/|\?|$)/.test(next) &&
    !next.includes("..");
  // Only reachable by visiting /waking/ by hand, since proxy.ts always sets
  // next. "/" rather than the old "/admin/": this page now stands in front of
  // a stranger's sign-in click too, and the landing page is the right place to
  // put someone whose destination we couldn't read.
  const dest = wanted ? next : "/";
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
