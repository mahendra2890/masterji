import { NextResponse, type NextRequest, type ProxyConfig } from "next/server";

// Render's free instance sleeps after 15 idle minutes, and its edge answers
// the first request after that with Render's own "SERVICE WAKING UP" log
// reel for the ~2 minutes the container takes to boot. Those logs are
// Render's, not ours: they never say how long the wait is, and someone who
// only wanted /admin/ reads them as a site that has broken. So we get in
// front of it — probe the API, and when it is still asleep serve our own
// note instead of proxying through to that page.
//
// Two navigations get this treatment, and they are the only two that leave
// this app for Django with a person watching: /admin, and the Google sign-in
// link. The sign-in link is the one that matters — components/SignIn.tsx
// points a plain <a> at /api/auth/google/login/, so clicking "Sign in" is a
// top-level navigation Render answers with its boot reel. That is a stranger's
// first click, and Render's logs are the worst thing to answer it with.
//
// The rest of /api/* is deliberately untouched, including the OAuth callback.
// The callback carries a one-time code from Google that expires, so parking it
// behind a poll risks a wait that ends in a dead code — a broken sign-in
// instead of a slow one. It is also the safe one to skip: nothing reaches the
// callback without the login redirect that just woke the server.
//
// Cost when the API is awake: one in-region round trip (tens of ms) on those
// two navigations. Only page loads — never the app's own /api/* calls,
// /static/*, or form posts, which the rewrites in next.config.ts still handle
// untouched.
//
// ?boot=logs opts back out: the note links to it, and the request then
// passes straight through to whatever Render is serving.

const API_URL = process.env.API_URL ?? "http://127.0.0.1:8000";

/** Awake and in-region this answers in well under 100ms. Asleep, Render's
 * edge answers with HTML instead — but a hung TCP connect is possible too,
 * so cap the wait rather than making the visitor sit through it. */
const PROBE_TIMEOUT_MS = 3000;

// Both slash forms of the login path: trailingSlash: true means the href in
// SignIn.tsx carries one, but a hand-typed or bookmarked URL may not, and a
// matcher is matched before that gets normalised.
export const config: ProxyConfig = {
  matcher: [
    "/admin",
    "/admin/:path*",
    "/api/auth/google/login",
    "/api/auth/google/login/",
  ],
};

export default async function proxy(req: NextRequest) {
  const { pathname, search, searchParams } = req.nextUrl;

  // Only the navigations a person is actually staring at: GET, wants HTML,
  // and hasn't asked for the boot logs on purpose. Everything else (the
  // login POST, the admin's own JSON calls) goes straight to Django.
  const wantsHtml = (req.headers.get("accept") ?? "").includes("text/html");
  if (req.method !== "GET" || !wantsHtml || searchParams.get("boot") === "logs") {
    return NextResponse.next();
  }

  if (await apiIsAwake()) return NextResponse.next();

  // A rewrite, not a redirect: the URL stays on /admin/, so reloading
  // retries the real thing once the server is up.
  const waking = new URL("/waking/", req.nextUrl);
  waking.searchParams.set("next", pathname + search);
  const res = NextResponse.rewrite(waking);
  // Nothing anywhere may keep this: a cached "waking up" note pinned to the
  // admin URL would outlive the boot it describes.
  res.headers.set("Cache-Control", "no-store");
  return res;
}

/** True only for a real answer from the Django process. A sleeping service
 * returns Render's holding page here — HTML, and often a cheerful 200 — so
 * the status code alone can't be trusted; the body has to be the health
 * payload from backend/config/urls.py. Reading it also frees the socket. */
async function apiIsAwake(): Promise<boolean> {
  try {
    const res = await fetch(`${API_URL}/api/health/`, {
      cache: "no-store",
      signal: AbortSignal.timeout(PROBE_TIMEOUT_MS),
    });
    const body = await res.text();
    return res.ok && body.includes('"ok"');
  } catch {
    return false; // timed out, refused, DNS — all "not ready for a visitor"
  }
}
