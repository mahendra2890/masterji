"use client";

// Browser-side auth helpers. Tokens live in httpOnly cookies, so JS never
// touches them — "credentials: include" tells fetch to send them along.
// /api/* is proxied to Django by next.config.ts rewrites, which keeps the
// cookies first-party.

export const API_URL = "";

export type SessionUser = {
  username: string;
  email: string;
  tone: "ENGLISH" | "HINGLISH";
};

/** Current user, or null when not signed in. Silently refreshes an
 * expired access token once before giving up. */
export async function fetchMe(): Promise<SessionUser | null> {
  const me = () => fetch(`${API_URL}/api/auth/me/`, { credentials: "include" });
  let res = await me();
  if (res.status === 401) {
    const refreshed = await fetch(`${API_URL}/api/auth/refresh/`, {
      method: "POST",
      credentials: "include",
    });
    if (!refreshed.ok) return null;
    res = await me();
  }
  return res.ok ? res.json() : null;
}

export async function updateTone(
  tone: SessionUser["tone"]
): Promise<SessionUser | null> {
  const res = await fetch(`${API_URL}/api/auth/me/`, {
    method: "PATCH",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tone }),
  });
  return res.ok ? res.json() : null;
}

export async function logout(): Promise<void> {
  await fetch(`${API_URL}/api/auth/logout/`, {
    method: "POST",
    credentials: "include",
  });
}
