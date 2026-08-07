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

export async function signOutAndLeave() {
  await apiLogout();
  window.location.href = "/login/";
}

/** Renders children only for signed-in users; everyone else is sent to
 * /login/ with a next param pointing back here. The signed-in user is
 * passed down so the app can render its own account chrome.
 *
 * While the backend is still booting there is no answer to act on, so the
 * gate waits behind the cold-start note and keeps asking. Rendering nothing
 * — the old behaviour — left a blank screen for the two minutes a Render
 * free instance takes to start; sending them to /login/ would be worse
 * still, since a signed-in visitor would look signed out. */
export default function AuthGate({
  children,
}: {
  children: (user: SessionUser) => React.ReactNode;
}) {
  const [user, setUser] = useState<SessionUser | null>(null);
  const [waking, setWaking] = useState(false);
  const pathname = usePathname();

  useEffect(() => {
    let stopped = false;
    const toLogin = () =>
      window.location.replace(`/login/?next=${encodeURIComponent(pathname)}`);

    (async () => {
      // Retry only while the backend is coming up. Anything Django actually
      // answered — including "no" — is final.
      while (!stopped) {
        try {
          const me = await fetchMe();
          if (stopped) return;
          if (me) setUser(me);
          else toLogin();
          return;
        } catch (err) {
          if (stopped) return;
          if (!(err instanceof ApiNotReady)) return toLogin();
          setWaking(true);
          await new Promise((resolve) => setTimeout(resolve, RETRY_EVERY_MS));
        }
      }
    })();

    return () => {
      stopped = true;
    };
  }, [pathname]);

  if (user) return <>{children(user)}</>;
  if (waking) {
    return (
      <main className={noteStyles.screen}>
        <WakingNote />
      </main>
    );
  }
  return null;
}
