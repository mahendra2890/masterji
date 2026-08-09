"use client";

import styles from "./dev-login.module.css";

// Local development only: the backend's dev-login endpoint 404s in prod,
// and this button never renders in a production build.
//
// Lives at the foot of the sign-in popup, which is where the rest of /login/
// went when that page was folded into the landing page. Running the signed-in
// app locally without Google credentials is the only thing it was ever for.
export default function DevLogin() {
  if (process.env.NODE_ENV === "production") return null;

  const signIn = async () => {
    const res = await fetch("/api/auth/dev-login/", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: "dev" }),
    });
    // A full navigation, so page.tsx re-reads the cookie that just arrived and
    // paints the app rather than this page. replace() rather than href:
    // "/" is where we already are, and a ?error= left over from a cancelled
    // Google attempt shouldn't be one Back press away.
    if (res.ok) window.location.replace("/");
  };

  return (
    <button className={styles.devBtn} onClick={signIn}>
      dev sign-in (local only)
    </button>
  );
}
