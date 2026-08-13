import { describe, expect, it } from "vitest";
import { resolveWakingTargets } from "./dest";

/** What these protect: the value in ?next= arrives from the URL bar, and the
 * waking page hands it to the browser as a redirect target. Everything below
 * is one of the two accepted destinations, or a way of pretending to be one. */
describe("resolveWakingTargets", () => {
  it("keeps the two paths proxy.ts actually sends here", () => {
    // The sign-in link, carrying its own query — the whole string round-trips
    // through this page's ?next= and has to come back out intact, or Django
    // loses track of where the visitor was headed after Google.
    expect(resolveWakingTargets("/api/auth/google/login/?next=%2F").dest).toBe(
      "/api/auth/google/login/?next=%2F",
    );
    expect(resolveWakingTargets("/admin/coach/changelogentry/").dest).toBe(
      "/admin/coach/changelogentry/",
    );
  });

  it("refuses anything that would send the browser off this origin", () => {
    // "//host" is protocol-relative: a browser reads it as another site, not
    // as a path. "/admin/.." resolves back out of /admin/ before the request
    // is made. The last two are prefixes that only look like the real ones.
    for (const hostile of [
      "//evil.com/",
      "https://evil.com/",
      "/admin/../elsewhere",
      "/adminish",
      "/api/auth/google/loginX",
    ]) {
      expect(resolveWakingTargets(hostile).dest, hostile).toBe("/");
    }
  });

  it("refuses the OAuth callback, which is deliberately not a destination", () => {
    // proxy.ts never parks the callback behind this page — its code from
    // Google is one-time and expires — so arriving here with one is not a
    // request this page honours. See the note in proxy.ts.
    expect(
      resolveWakingTargets("/api/auth/google/callback/?code=abc").dest,
    ).toBe("/");
  });

  it("falls back when there is no next at all", () => {
    // Only reachable by visiting /waking/ by hand: proxy.ts always sets one.
    expect(resolveWakingTargets(undefined).dest).toBe("/");
    expect(resolveWakingTargets("").dest).toBe("/");
  });

  it("joins boot=logs with the separator the destination has left free", () => {
    // The sign-in path arrives with a query already on it, so a second "?"
    // would make the opt-out link a different URL than the one it opts out
    // of — and the visitor would land back on the note they just left.
    expect(resolveWakingTargets("/api/auth/google/login/?next=%2F").logs).toBe(
      "/api/auth/google/login/?next=%2F&boot=logs",
    );
    expect(resolveWakingTargets("/admin/").logs).toBe("/admin/?boot=logs");
  });
});
