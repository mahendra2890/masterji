/** Where the waking page points the browser.
 *
 * Split out of page.tsx so it can be tested directly (dest.test.ts): the value
 * it reads is attacker-controllable — anyone can type /waking/?next=whatever —
 * and it ends up as a redirect target, which is the one kind of decision here
 * that is worth pinning rather than eyeballing.
 */

/** The only two destinations proxy.ts ever parks behind this page. Anchored at
 * both ends: the trailing group is what stops "/adminish" and
 * "/api/auth/google/loginX" from passing as the paths they resemble, and "?" is
 * in it so the sign-in path can arrive with its own query attached. */
const ACCEPTED = /^\/(admin|api\/auth\/google\/login)(\/|\?|$)/;

export function resolveWakingTargets(next: string | undefined): {
  /** Where to send the browser once the backend answers. */
  dest: string;
  /** The same place, opting out of this note and back into whatever Render is
   * serving. proxy.ts checks for boot=logs and passes those through. */
  logs: string;
} {
  // Rejected: a protocol-relative "//host", which a browser reads as another
  // site; and "/admin/../elsewhere", which it resolves back out of /admin/
  // before the request is ever made. Both are paths only by appearance.
  const wanted = Boolean(next) && ACCEPTED.test(next!) && !next!.includes("..");
  // The fallback is only reachable by visiting /waking/ by hand, since proxy.ts
  // always sets next. "/" rather than "/admin/": this page stands in front of a
  // stranger's sign-in click now, and the landing page is the right place to
  // put someone whose destination could not be read.
  const dest = wanted ? next! : "/";
  return { dest, logs: `${dest}${dest.includes("?") ? "&" : "?"}boot=logs` };
}
