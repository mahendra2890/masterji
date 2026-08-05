import type { Metadata } from "next";
import Home from "./Home";

export const metadata: Metadata = {
  title: "Masterji — the coach who makes you ship",
  description:
    "One goal, earned phases, daily proof. A tough-love AI execution coach " +
    "for first-time builders.",
};

export default function Page() {
  return <Home />;
}
