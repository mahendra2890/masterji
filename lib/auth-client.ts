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
  mode: "COACH" | "THINKING";
};

/** The backend hasn't answered anything Django wrote — Render's free
 * instance is still coming up. Kept apart from a 401 on purpose: a boot in
 * progress is "wait", not "signed out", and the difference is what stops an
 * idle tab from throwing a signed-in user back to /login/. */
export class ApiNotReady extends Error {}

/** Past this, assume the instance is booting rather than slow. Warm, these
 * calls come back in a few hundred ms; the caller retries, so guessing
 * early costs a retry and guessing late costs a blank screen. */
const READY_TIMEOUT_MS = 5000;

/** Current user, or null when not signed in. Silently refreshes an
 * expired access token once before giving up. Throws ApiNotReady while the
 * backend is still starting. */
export async function fetchMe(): Promise<SessionUser | null> {
  const me = () => ask("/api/auth/me/");
  let res = await me();
  if (res.status === 401) {
    const refreshed = await ask("/api/auth/refresh/", { method: "POST" });
    if (!refreshed.ok) return null;
    res = await me();
  }
  return res.ok ? res.json() : null;
}

/** One auth call, with "the server isn't up yet" separated from every
 * answer Django can give. A sleeping instance is the loud case: Render's
 * edge returns its own holding page with a cheerful 200, so an unchecked
 * res.json() would throw and read as a dead session. Every view in
 * accounts/views.py answers JSON, 401s included — anything else isn't
 * Django talking. */
async function ask(path: string, init: RequestInit = {}): Promise<Response> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      credentials: "include",
      signal: AbortSignal.timeout(READY_TIMEOUT_MS),
      ...init,
    });
  } catch {
    throw new ApiNotReady(); // aborted, offline, DNS, connection refused
  }
  if (!(res.headers.get("content-type") ?? "").includes("application/json")) {
    throw new ApiNotReady();
  }
  return res;
}

/** How the coach talks — language, and which side of the table he's on.
 * Both live on the user rather than on the turn: a builder who asked to be
 * spoken to a certain way shouldn't have to ask again tomorrow. */
export type CoachPrefs = Pick<SessionUser, "tone" | "mode">;

export async function updatePrefs(
  patch: Partial<CoachPrefs>
): Promise<SessionUser | null> {
  const res = await fetch(`${API_URL}/api/auth/me/`, {
    method: "PATCH",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  return res.ok ? res.json() : null;
}

export async function logout(): Promise<void> {
  await fetch(`${API_URL}/api/auth/logout/`, {
    method: "POST",
    credentials: "include",
  });
}
