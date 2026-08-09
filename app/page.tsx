import type { Metadata } from "next";
import { cookies } from "next/headers";
import Home from "./Home";
import Landing from "./Landing";

export const metadata: Metadata = {
  title: "Masterji — the coach who makes you ship",
  description:
    "One goal, earned phases, daily proof. A tough-love AI execution coach " +
    "for first-time builders.",
};

/** Where to send someone after Google, and the only shape allowed: a
 * same-site path. It arrives in a query string, and it leaves inside the
 * sign-in link's href, so an unchecked "//evil.example" would be an open
 * redirect wearing our own domain. Django re-checks it (oauth._safe_next);
 * this is the near end of the same rule, and the same one app/waking/page.tsx
 * applies to its own ?next=. */
function safeNext(value: string | undefined): string {
  return value && value.startsWith("/") && !value.startsWith("//") ? value : "/";
}

export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; next?: string }>;
}) {
  const { error, next } = await searchParams;

  // Which of the two pages to paint FIRST, and nothing more. The access
  // cookie is httpOnly and path "/", so it reaches this route; the refresh
  // cookie is scoped to /api/auth/ and never does. Neither is verified here —
  // that is AuthGate's job, and it overrules this either way.
  //
  // The question being asked is only "was somebody using this browser
  // recently?", because the cost of guessing wrong is a paint: guess "app"
  // for a stranger and they get a blank screen while we ask Django; guess
  // "signedOut" for a returning builder and they watch a landing page flash
  // past on the way to their own dashboard.
  //
  // ?error is the one case where a stale cookie doesn't get the benefit of
  // the doubt. Whoever is holding it just came back from Google without a
  // session, so the answer to "are they signed in" is already known to be no
  // — and painting "app" would hide the note explaining what happened behind
  // a round trip that can only confirm it.
  const usedRecently = (await cookies()).has("access_token");
  return (
    <Home
      landing={<Landing error={error} next={safeNext(next)} />}
      firstPaint={usedRecently && !error ? "app" : "signedOut"}
    />
  );
}
