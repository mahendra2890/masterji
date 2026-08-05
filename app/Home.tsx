"use client";

import AuthGate from "@/components/AuthGate";
import Masterji from "./Masterji";

// The render-prop into AuthGate must be created client-side — a server
// component can't pass a function across the boundary.
export default function Home() {
  return <AuthGate>{(user) => <Masterji user={user} />}</AuthGate>;
}
