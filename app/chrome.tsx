"use client";

// Account chrome, and the one chip both screens draw.
//
// These are the pieces the onboarding screen and the dashboard both put on the
// page: the way out, the way to the tour, and how a closed idea reads in the
// "Behind you" list. They were declared above `Masterji()` when there was one
// component; with two screens they belong to neither, and a copy each is how
// two headers start to disagree.

import { useState } from "react";
import { signOutAndLeave } from "@/components/AuthGate";
import type { Retirement } from "@/lib/coach-api";
import styles from "./masterji.module.css";

/** How each closed idea reads, in one chip. The wording states what the record
 * shows, never a judgement of the person. */
export const CLOSED_CHIP: Record<
  Retirement["readsAs"],
  { label: string; className: (s: Record<string, string>) => string }
> = {
  ACHIEVED: { label: "achieved", className: (s) => s.chipGood },
  UNVERIFIED: { label: "achieved · unverified", className: (s) => s.chipNone },
  INVALIDATED: { label: "tested → dead", className: (s) => s.chipTested },
  UNTESTED: { label: "untested", className: (s) => s.chipNone },
};

/** The way out, with a press between the thumb and the door.
 *
 * It was a 16px-tall underlined link in the top-right of a phone — the thumb's
 * own parking spot — 12px from "What's new", firing on the first press. The
 * cost of that miss isn't a wasted tap: the session is gone and the way back is
 * a full round trip through Google, on the one product whose entire premise is
 * that you come back tomorrow.
 *
 * So: a target you can mean to hit, and a second press. The first press only
 * changes what the button says, which is the cheapest way to make an accident
 * visible, and it undoes itself the moment focus moves — nobody is left holding
 * a question they didn't ask. A timer would do neither well: it either fires
 * while they're still deciding or leaves the question up long after they
 * stopped caring.
 *
 * The underline goes too. It made the exit the only underlined thing in the
 * header, which is a strange honour for the door.
 */
export function SignOutButton() {
  const [asking, setAsking] = useState(false);
  return (
    <button
      className={asking ? styles.signOutAsking : styles.signOut}
      onBlur={() => setAsking(false)}
      onKeyDown={(e) => e.key === "Escape" && setAsking(false)}
      onClick={() => (asking ? signOutAndLeave() : setAsking(true))}
      /* The visible label stays inside one fixed box — see .signOut's
         min-width — so the press doesn't slide the rest of the header
         sideways under the finger that made it. The sentence the question
         mark is short for lives here, for anyone not reading pixels. */
      aria-label={asking ? "Press again to sign out" : "Sign out"}
      title={asking ? "Press again to sign out" : undefined}
    >
      {asking ? "sign out?" : "sign out"}
    </button>
  );
}

/** The way back to the tour, from inside the account.
 *
 * /demo/ was reachable from exactly one place — the sign-in popup — so the
 * four screens that explain this product disappeared the moment somebody had
 * an account. That is the wrong way round: a stranger can always press the
 * button again, and the builder who actually needs the explanation is the one
 * three days in, looking at a control whose second option they have never
 * understood. The tour is the only place "Think with me" is explained at all
 * (Tour.tsx says so itself), and it was behind a sign-out.
 *
 * A plain quiet link beside "What's new" rather than anything new: the two
 * are the same kind of thing — a word in the account chrome that opens an
 * explanation — and the mode bar over the composer is a control, not a help
 * page, which is where this emphatically does not go.
 *
 * Padded for the thumb and pulled back by the same amount, the way
 * .historyRow does it: a 24px target that occupies exactly as much of the
 * header as the word does.
 */
export function TourLink() {
  return (
    <a
      className={styles.tourLink}
      href="/demo/"
      title="The guided tour of these screens"
    >
      How it works
    </a>
  );
}
