"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { fetchMe, logout as apiLogout, type SessionUser } from "@/lib/auth-client";

export async function signOutAndLeave() {
  await apiLogout();
  window.location.href = "/login/";
}

/** Renders children only for signed-in users; everyone else is sent to
 * /login/ with a next param pointing back here. The signed-in user is
 * passed down so the app can render its own account chrome. */
export default function AuthGate({
  children,
}: {
  children: (user: SessionUser) => React.ReactNode;
}) {
  const [user, setUser] = useState<SessionUser | null>(null);
  const pathname = usePathname();

  useEffect(() => {
    let cancelled = false;
    const toLogin = () =>
      window.location.replace(`/login/?next=${encodeURIComponent(pathname)}`);
    fetchMe()
      .then((me) => {
        if (cancelled) return;
        if (me) setUser(me);
        else toLogin();
      })
      .catch(() => {
        if (!cancelled) toLogin();
      });
    return () => {
      cancelled = true;
    };
  }, [pathname]);

  if (!user) return null;
  return <>{children(user)}</>;
}
