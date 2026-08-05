import styles from "./login.module.css";
import DevLogin from "./DevLogin";

export const metadata = { title: "Sign in — Masterji" };

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; next?: string }>;
}) {
  const { error, next } = await searchParams;

  return (
    <main className={styles.main}>
      <p className={styles.wordmark}>मास्टरजी</p>
      <h1 className={styles.title}>Masterji</h1>
      <p className={styles.sub}>
        The coach who makes you ship. One goal, earned phases, daily proof —
        no hiding in planning.
      </p>
      <a
        className={styles.googleBtn}
        href={`/api/auth/google/login/?next=${encodeURIComponent(next ?? "/")}`}
      >
        Continue with Google
      </a>
      {error === "cancelled" && (
        <p className={styles.error}>
          Login was cancelled — Masterji will pretend not to notice. Once.
        </p>
      )}
      <a className={styles.back} href="/demo/">
        or watch the demo first →
      </a>
      <DevLogin />
    </main>
  );
}
