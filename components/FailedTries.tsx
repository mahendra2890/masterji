import type { ProofAttempt } from "@/lib/coach-api";
import styles from "@/app/masterji.module.css";

/** The pushed-back tries behind a check-in's current proof, folded away.
 *
 * Only the proof that stands is shown by default — the misses are on the
 * record (they're honest work, and Masterji's objections teach), but they
 * read as history, not as part of tonight's answer. Used by the TODAY card
 * and the closed-idea drill-in.
 */
export default function FailedTries({ attempts }: { attempts: ProofAttempt[] }) {
  if (attempts.length === 0) return null;
  return (
    <details className={styles.tries}>
      <summary>
        {attempts.length === 1
          ? "1 earlier try, pushed back"
          : `${attempts.length} earlier tries, pushed back`}
      </summary>
      {attempts.map((a) => (
        <div key={a.id} className={styles.try}>
          <p className={styles.tryText}>{a.text}</p>
          {a.url && (
            <a
              className={styles.tryUrl}
              href={a.url}
              target="_blank"
              rel="noreferrer noopener"
            >
              {a.url}
            </a>
          )}
          {a.imageUrl && (
            /* eslint-disable-next-line @next/next/no-img-element --
               this redirects to a presigned URL on a host that isn't known at
               build time, so there is nothing for next/image to optimise. */
            <img
              className={styles.tryImage}
              src={a.imageUrl}
              alt="The screenshot submitted with this pushed-back try"
            />
          )}
          {a.reaction && <p className={styles.tryReaction}>म — {a.reaction}</p>}
        </div>
      ))}
    </details>
  );
}
