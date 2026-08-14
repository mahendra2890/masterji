import { describe, expect, it } from "vitest";
import { firstPaintFor } from "./first-paint";

/** What these protect: the two properties app/page.tsx's comment says were
 * paid for, and which the dashboard shell had to keep. A stranger must never
 * wait on Django — so no cookie means the landing, immediately, out of the
 * HTML. A returning builder must never watch the landing flash past on the way
 * to their own dashboard — so a cookie means the app's own frame instead.
 *
 * The ?error row is the one that would go quietly wrong. Whoever holds a stale
 * cookie after a cancelled Google sign-in would be shown a dashboard shell,
 * and the note telling them what happened is on the page they didn't get. */
describe("firstPaintFor", () => {
  it("paints the landing for a browser with no access cookie", () => {
    expect(firstPaintFor({ hasAccessCookie: false, hasError: false })).toBe(
      "signedOut"
    );
  });

  it("paints the app for a browser that was using it recently", () => {
    expect(firstPaintFor({ hasAccessCookie: true, hasError: false })).toBe(
      "app"
    );
  });

  it("paints the landing after a failed sign-in, cookie or not", () => {
    // The answer to "are they signed in" is already known here, so the cookie
    // does not get to override it and hide the note behind a round trip.
    expect(firstPaintFor({ hasAccessCookie: true, hasError: true })).toBe(
      "signedOut"
    );
    expect(firstPaintFor({ hasAccessCookie: false, hasError: true })).toBe(
      "signedOut"
    );
  });
});
