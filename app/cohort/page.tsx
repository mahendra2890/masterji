import type { Metadata } from "next";
import Cohort from "./Cohort";

// Not indexed, and not because the page is secret — it is unreachable without
// a session, so a crawler would only ever see the signed-out shell. The one
// thing an index of it could produce is a search result carrying a cohort's
// name next to a builder's, which is a page nobody agreed to be on.
export const metadata: Metadata = {
  title: "Your cohort — Masterji",
  description:
    "What your cohort actually did: proofs that cleared a gate, conversations " +
    "with real people, days on the record. Nothing self-reported.",
  robots: { index: false, follow: false },
};

export default function CohortPage() {
  return <Cohort />;
}
