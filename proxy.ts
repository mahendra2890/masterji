import { NextResponse, type NextRequest, type ProxyConfig } from "next/server";

// The API scales to zero when idle, and a wake costs about half a minute
// (measured: 23.9s — components/WakingNote.tsx has the method). So we probe
// the API, and when it is still asleep serve our own note instead of proxying
// a visitor into a wait with nothing on the screen.
//
// This was originally written against Render, where the reason was sharper:
// Render's edge answered a sleeping service with its own "SERVICE WAKING UP"
// log reel, which says nothing about how long the wait is and reads as a site
// that has broken. Cloud Run does no such thing — it holds the request until
// the container answers. What is left is the plain one: half a minute of
// nothing is still worth explaining, and ?boot=logs below is now a vestige of
// the Render page it used to opt back into.
//
// Two navigations get this treatment, and they are the only two that leave
// this app for Django with a person watching: /admin, and the Google sign-in
// link. The sign-in link is the one that matters — components/SignIn.tsx
// points a plain <a> at /api/auth/google/login/, so clicking "Sign in" is a
// top-level navigation Render answers with its boot reel. That is a stranger's
// first click, and Render's logs are the worst thing to answer it with.
//
// The rest of /api/* never gets the PROBE, including the OAuth callback. The
// callback carries a one-time code from Google that expires, so parking it
// behind a poll risks a wait that ends in a dead code — a broken sign-in
// instead of a slow one. It is also the safe one to skip: nothing reaches the
// callback without the login redirect that just woke the server.
//
// (It used to be that the rest of /api/* was not matched at all. It is now —
// see the second block below — but only to be stamped. `watched` is what keeps
// the probe on the two navigations, so everything written above still holds.)
//
// Cost when the API is awake: one in-region round trip (tens of ms) on those
// two navigations. Only page loads — never the app's own /api/* calls,
// /static/*, or form posts, which the rewrites in next.config.ts still handle
// untouched.
//
// ?boot=logs opts back out: the note links to it, and the request then
// passes straight through to whatever Render is serving.

// ---------------------------------------------------------------------------
// The second job this file grew: signing what we forward.
//
// The Cloud Run host answers the public internet directly, so Django had two
// front doors with different numbers of proxies in front of them — and DRF
// keys every anonymous ceiling on a count of those proxies. One integer, two
// doors, and an attacker is the only caller who gets to pick which one they
// use (#317; backend/accounts/middleware.py EdgeSecretMiddleware is the other
// half of this, and carries the full argument).
//
// So every request this app forwards to Django now carries a shared secret,
// and Django refuses anything that does not. That is why the matcher below
// grew from two navigations to everything that crosses the boundary: it is no
// longer only about waking a sleeping API, it is about being the only way in.
//
// WHY THE HEADER IS ATTACHED HERE AND NOT IN next.config.ts: rewrites cannot
// add request headers. They are still what does the proxying — this only
// stamps the request on its way past, which keeps the rewrite table, its
// ordering, and NDJSON streaming exactly as they were.
//
// Unset is inert, on both sides. Local development runs without it.
//
// .trim() because this value is pasted into a dashboard by hand and a trailing
// newline is invisible in every UI that shows it back to you. Django strips its
// side too; both must match byte for byte, and a stray "\n" on either one is a
// 403 for the whole API with nothing anywhere saying why.
const EDGE_SECRET = (process.env.EDGE_SHARED_SECRET ?? "").trim();
const EDGE_HEADER = "x-masterji-edge";

const API_URL = process.env.API_URL ?? "http://127.0.0.1:8000";

/** Awake and in-region this answers in well under 100ms. Asleep, Render's
 * edge answers with HTML instead — but a hung TCP connect is possible too,
 * so cap the wait rather than making the visitor sit through it. */
const PROBE_TIMEOUT_MS = 3000;

// Everything that leaves this app for Django, because everything that leaves
// this app for Django has to be signed. The four entries that were here before
// are the two navigations the waking note is for (/admin and the Google
// sign-in link, both slash forms — trailingSlash: true means the href in
// SignIn.tsx carries one, but a hand-typed or bookmarked URL may not, and a
// matcher is matched before that gets normalised); the rest mirror the rewrite
// table in next.config.ts.
export const config: ProxyConfig = {
  matcher: [
    "/admin",
    "/admin/:path*",
    "/api/auth/google/login",
    "/api/auth/google/login/",
    "/api/:path*",
    "/static/:path*",
  ],
};

export default async function proxy(req: NextRequest) {
  const { pathname, search, searchParams } = req.nextUrl;

  // Only the navigations a person is actually staring at get the waking note:
  // GET, wants HTML, hasn't asked for the boot logs on purpose, and is one of
  // the two paths that leaves this app with somebody watching. Everything else
  // (the app's own /api/* calls, the login POST, the admin's JSON, /static/*)
  // is only here to be signed and goes straight to Django.
  const wantsHtml = (req.headers.get("accept") ?? "").includes("text/html");
  const watched = pathname.startsWith("/admin") || isGoogleLogin(pathname);
  if (
    !watched ||
    req.method !== "GET" ||
    !wantsHtml ||
    searchParams.get("boot") === "logs"
  ) {
    return signed(req);
  }

  if (await apiIsAwake()) return signed(req);

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

/** Pass the request through to the rewrite that will proxy it, stamped so
 * Django knows it came from us. `NextResponse.next({ request: { headers } })`
 * is the only place a request header can be added — next.config.ts's rewrites
 * carry it, but cannot create it. */
function signed(req: NextRequest) {
  if (!EDGE_SECRET) return NextResponse.next();
  const headers = new Headers(req.headers);
  // set, not append: a client that sent this header themselves must not be
  // able to leave their value in front of ours.
  headers.set(EDGE_HEADER, EDGE_SECRET);
  return NextResponse.next({ request: { headers } });
}

function isGoogleLogin(pathname: string): boolean {
  return (
    pathname === "/api/auth/google/login" || pathname === "/api/auth/google/login/"
  );
}

/** True only for a real answer from the Django process. A sleeping service
 * returns Render's holding page here — HTML, and often a cheerful 200 — so
 * the status code alone can't be trusted; the body has to be the health
 * payload from backend/config/urls.py. Reading it also frees the socket.
 *
 * Deliberately NOT stamped with the edge secret. `/api/health/` is exempt from
 * the gate (EdgeSecretMiddleware names it, along with the hourly nudge tick),
 * because the keep-warm ping and the deploy-time check call it directly too.
 * Adding the header here would work and would quietly make this the only
 * caller that needs it — the next person to add a prober would be the one who
 * found out it does not. */
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
