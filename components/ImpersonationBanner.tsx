"use client";

// The one thing on screen that is not the builder's.
//
// An operator viewing somebody's account sees their dashboard, their idea,
// their evenings — a screen designed to be indistinguishable from being
// signed in, because that is the point of it. So the fact that it is not your
// account has to be stated somewhere that cannot be scrolled away from or
// mistaken for part of the product, which is why this is fixed to the top of
// the viewport and coloured like a warning rather than like the app.
//
// It renders for exactly one reader. A builder can never see it: the flag
// comes from a claim on the operator's own token (accounts/impersonation.py),
// so there is no state in which this appears on a real session.

import styles from "./impersonation-banner.module.css";

export default function ImpersonationBanner({
  username,
  operator,
}: {
  username: string;
  operator: string;
}) {
  return (
    <div className={styles.banner} role="status">
      <strong>Viewing as {username}</strong>
      <span>
        read-only · signed in as {operator} · ends when the session expires
      </span>
    </div>
  );
}
