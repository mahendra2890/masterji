"use client";

import AuthGate from "@/components/AuthGate";
import Masterji from "./Masterji";

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
  return (
    <AuthGate signedOut={landing} firstPaint={firstPaint}>
      {(user) => <Masterji user={user} />}
    </AuthGate>
  );
}
