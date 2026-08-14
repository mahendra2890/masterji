import type { Metadata } from "next";
import SharedRecord from "./SharedRecord";

// Deliberately not a per-record title. The metadata is static because the page
// is not: generating it would mean fetching the record on the server, and this
// route is reachable by anybody holding the link — including crawlers, which
// would then have the goal's title in an index the builder never agreed to.
// The switch shares a page with one person, not a listing.
export const metadata: Metadata = {
  title: "A record on Masterji",
  description:
    "What one builder actually did: the phase they reached, the proofs they " +
    "banked, and how many of them came from talking to real people. Every " +
    "number came through a gate.",
  robots: { index: false, follow: false },
};

export default function RecordPage() {
  return <SharedRecord />;
}
