"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import {
  ApiNotReady,
  fetchMe,
  logout as apiLogout,
  type SessionUser,
} from "@/lib/auth-client";
import WakingNote from "@/components/WakingNote";
import noteStyles from "@/components/waking-note.module.css";

const RETRY_EVERY_MS = 3000;

/** Sign out, then go to "/" — the landing page, not the sign-in wall.
 *
 * Sending them to /login/ was right back when "/" was the app and nothing
 * else: there was nowhere else to put someone without a session. But it
 * answered "I'm done" with a Google button, which reads as "sign in again"
 * — the one thing they just said they didn't want.
 *
 * "/" is now a real page, and the door back in is the Sign in link in its
 * corner. Nothing flashes on the way: logout clears the access cookie, so
 * page.tsx's first paint is already the landing, and AuthGate leaves a
 * visitor there once Django confirms there's no session.
 */
export async function signOutAndLeave() {
  await apiLogout();
  window.location.href = "/";
}

/** Renders children only for signed-in users. The signed-in user is passed
 * down so the app can render its own account chrome.
 *
 * While the backend is still booting there is no answer to act on, so the
 * gate waits behind the cold-start note and keeps asking. Rendering nothing
 * — the old behaviour — left a blank screen for the two minutes a Render
 * free instance takes to start; sending them to /login/ would be worse
 * still, since a signed-in visitor would look signed out.
 *
 * `signedOut` is the page to show when there turns out to be no session. Given
 * one, nobody is redirected anywhere: a stranger arriving at "/" is the normal
 * case, and bouncing them to a sign-in wall meant the entire product a
 * first-time visitor ever saw was a button asking for their Google account.
 * Without one, the old redirect stands, which is right for a URL that is only
 * ever the app.
 */
export default function AuthGate({
  children,
  signedOut,
  /** What to paint before the answer arrives. "app" paints nothing, which is
   * correct for a returning builder — they must not watch a landing page
   * flash past on the way to their own dashboard. "signedOut" paints that
   * page immediately, which is correct for a stranger, whose whole visit
   * would otherwise begin with a blank screen and a round trip. The caller
   * decides from the auth cookie; this only decides what to draw first, and
   * the answer below still overrules it either way. */
  firstPaint = "app",
}: {
  children: (user: SessionUser) => React.ReactNode;
  signedOut?: React.ReactNode;
  firstPaint?: "app" | "signedOut";
}) {
  const [user, setUser] = useState<SessionUser | null>(null);
  const [waking, setWaking] = useState(false);
  // What Django's "nobody" turned out to mean here. Null until it has
  // answered — the difference between "nobody is signed in" and "we haven't
  // asked", which is the difference between showing a page and showing
  // nothing yet.
  const [noOne, setNoOne] = useState<"stay" | "leaving" | null>(null);
  const pathname = usePathname();
  // A node is a new object on every render, so the effect below depends on
  // whether there is one rather than on the node itself — otherwise the gate
  // would re-ask Django who you are on every re-render.
  const hasSignedOutPage = Boolean(signedOut);

  useEffect(() => {
    let stopped = false;
    const noSession = () => {
      // A stranger stays on the page written for them. Someone who arrived
      // with an auth cookie is a returning builder whose session has since
      // died, and they wanted their dashboard — hand them the sign-in page
      // they were always given rather than a pitch for the product they
      // already use.
      const leaving = !hasSignedOutPage || firstPaint === "app";
      setNoOne(leaving ? "leaving" : "stay");
      if (leaving) {
        window.location.replace(`/login/?next=${encodeURIComponent(pathname)}`);
      }
    };

    (async () => {
      // Retry only while the backend is coming up. Anything Django actually
      // answered — including "no" — is final.
      while (!stopped) {
        try {
          const me = await fetchMe();
          if (stopped) return;
          if (me) setUser(me);
          else noSession();
          return;
        } catch (err) {
          if (stopped) return;
          if (!(err instanceof ApiNotReady)) return noSession();
          setWaking(true);
          await new Promise((resolve) => setTimeout(resolve, RETRY_EVERY_MS));
        }
      }
    })();

    return () => {
      stopped = true;
    };
  }, [pathname, hasSignedOutPage, firstPaint]);

  if (user) return <>{children(user)}</>;

  // A visitor who was given a signed-out page gets it instead of the
  // cold-start note: the landing needs no backend, and a stranger meeting
  // "the server is waking up" as their first impression of the product is the
  // worst version of an honest message. Never while a redirect is in flight —
  // that would flash a landing page at someone on their way to sign in.
  if (signedOut && (firstPaint === "signedOut" || noOne === "stay")) {
    return <>{signedOut}</>;
  }
  if (waking) {
    return (
      <main className={noteStyles.screen}>
        <WakingNote />
      </main>
    );
  }
  return null;
}
