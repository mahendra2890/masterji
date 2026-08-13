import { describe, expect, it } from "vitest";
import { hasUnseen } from "./changelog-seen";

/** What these protect: the dot is the only nagging affordance in the header,
 * and it is rendered on the landing page, the tour and the app shell — so it
 * is also on the commit screen, which is the first screen after signup and has
 * exactly one job. The rule has to mean "something shipped since you last
 * looked" in every state, and the two empty strings are where it stopped
 * meaning that. */
describe("hasUnseen", () => {
  it("stays dark for a browser holding no stamp", () => {
    // The first-run case, and the bug: "" sorts before every real date, so a
    // string comparison alone lights the dot for somebody who has never seen
    // the product, about changes that shipped before they existed.
    expect(hasUnseen("", "2026-08-14")).toBe(false);
  });

  it("stays dark until both halves are known", () => {
    // `null` is the render before the mount effect reads storage — it has to
    // match the server's markup, which has no dot in it. `""` for latest is
    // the mount fetch still in flight, or failed: no newest entry, nothing to
    // be behind.
    expect(hasUnseen(null, "2026-08-14")).toBe(false);
    expect(hasUnseen("2026-08-01", "")).toBe(false);
    expect(hasUnseen(null, "")).toBe(false);
    expect(hasUnseen("", "")).toBe(false);
  });

  it("lights when something shipped after the stamp", () => {
    expect(hasUnseen("2026-08-13", "2026-08-14")).toBe(true);
    // Across both boundaries a naive comparison gets wrong, and the reason
    // `shipped_on` is stored as an ISO string rather than formatted.
    expect(hasUnseen("2026-07-31", "2026-08-01")).toBe(true);
    expect(hasUnseen("2025-12-31", "2026-01-01")).toBe(true);
  });

  it("stays dark on the entry it was stamped with", () => {
    // Both the stamp written on first mount and the one written on open land
    // here, and this is what makes the dot go out and stay out.
    expect(hasUnseen("2026-08-14", "2026-08-14")).toBe(false);
  });

  it("stays dark when the stamp is ahead of the list", () => {
    // Not reachable through the UI, but it is what a shorter preview or a
    // withdrawn entry (`is_active: false`) looks like from here, and "ahead"
    // is not "behind".
    expect(hasUnseen("2026-08-14", "2026-08-13")).toBe(false);
  });
});
