/** Which of the two pages "/" paints before anyone has asked Django anything.
 *
 * Lifted out of app/page.tsx so the rule can be read and tested on its own —
 * the route around it is a server component, and this repo has no way to
 * render one in a test (#117: no jsdom, no rendering harness). The comment
 * that explains WHY the question is only "was somebody using this browser
 * recently?" lives at the call site, with the cookie it reads.
 *
 * Both answers now paint a full page: "signedOut" is the landing, "app" is the
 * dashboard shell. Before the shell existed "app" painted nothing at all, and
 * a wrong guess here cost a returning builder every millisecond of the client
 * bundle and a round trip (#239).
 */
export type FirstPaint = "app" | "signedOut";

export function firstPaintFor({
  hasAccessCookie,
  hasError,
}: {
  /** The access cookie is present. Never validated — it is httpOnly, it
   * reaches this route, and asking Django whether it is real is the thing this
   * decision exists to avoid doing before the first paint. */
  hasAccessCookie: boolean;
  /** ?error — they just came back from Google without a session. */
  hasError: boolean;
}): FirstPaint {
  // A stale cookie gets the benefit of the doubt everywhere except here.
  // Whoever holds it just failed to sign in, so "are they signed in" is
  // already known to be no, and painting the app would hide the note
  // explaining what happened behind a round trip that can only confirm it.
  if (hasError) return "signedOut";
  return hasAccessCookie ? "app" : "signedOut";
}
