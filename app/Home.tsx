"use client";

import { useEffect } from "react";
import dynamic from "next/dynamic";
import AuthGate from "@/components/AuthGate";
import DashboardShell from "./DashboardShell";

// Loaded when there is a user to render, not when this module is parsed.
//
// It used to be a plain `import Masterji from "./Masterji"`, which put the
// signed-in app in the eager chunk set for "/" — so a stranger who will only
// ever read the landing page downloaded the whole dashboard to do it, measured
// at 17KB gzip of "/"'s 216KB and requested on first load with no cookie
// (#240). The graph behind it grew 38% in a day; nothing about the old shape
// slowed that down.
//
// No `ssr: false`. The server still renders whatever AuthGate decides to draw,
// which for a returning builder is the shell — and a shell that only appeared
// after hydration would give back the whole of #239.
const Masterji = dynamic(() => import("./Masterji"));

// The render-prop into AuthGate must be created client-side — a server
// component can't pass a function across the boundary.
//
// `landing` comes the other way: page.tsx renders it on the server and hands
// it down as an already-built node, so the landing page stays a server
// component and none of it lands in this bundle.
export default function Home({
  landing,
  firstPaint,
}: {
  landing: React.ReactNode;
  firstPaint: "app" | "signedOut";
}) {
  // Splitting the dashboard out pays for itself on the landing and charges the
  // signed-in path for it: AuthGate renders `children` only once fetchMe has
  // answered, so the chunk request would start AFTER the round trip rather
  // than beside it, and a builder would wait for one and then the other. That
  // is the regression #240 warned about, and this is the whole of the fix —
  // the same import(), started at mount, on the one path that is going to need
  // it. Module loads are memoised, so `dynamic` above finds it already in
  // flight or already there.
  //
  // Keyed on `firstPaint` rather than run unconditionally, because "the cookie
  // is absent" is the one case we know will not need this, and that case is
  // the entire point of the split.
  useEffect(() => {
    if (firstPaint === "app") import("./Masterji");
  }, [firstPaint]);

  return (
    <AuthGate
      signedOut={landing}
      firstPaint={firstPaint}
      loading={<DashboardShell />}
    >
      {(user) => <Masterji user={user} />}
    </AuthGate>
  );
}
