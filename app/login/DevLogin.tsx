"use client";

import styles from "./login.module.css";

// Local development only: the backend's dev-login endpoint 404s in prod,
// and this button never renders in a production build.
export default function DevLogin() {
  if (process.env.NODE_ENV === "production") return null;

  const signIn = async () => {
    const res = await fetch("/api/auth/dev-login/", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: "dev" }),
    });
    if (res.ok) window.location.href = "/";
  };

  return (
    <button className={styles.devBtn} onClick={signIn}>
      dev sign-in (local only)
    </button>
  );
}
