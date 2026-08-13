import { describe, expect, it } from "vitest";
import { trapTarget } from "./dialog-focus";

/** What these protect: four modals in this app declare `aria-modal="true"`,
 * which tells a screen reader the rest of the page is inert. Tab is what makes
 * that true or a lie, and this is the arithmetic behind it — where focus goes
 * next, given what the dialog holds and where focus is now. `null` means the
 * browser's own Tab order is already right and the handler must not touch it,
 * which is as load-bearing as the wraps: a trap that intercepts every Tab is a
 * trap that breaks typing inside the dialog. */
describe("trapTarget", () => {
  const items = ["close", "link", "submit"];

  it("wraps at both ends instead of leaving the dialog", () => {
    // The last element forward and the first backward are the two exits, and
    // the two the browser would otherwise take into the dashboard behind.
    expect(trapTarget(items, "submit", false)).toBe("close");
    expect(trapTarget(items, "close", true)).toBe("submit");
  });

  it("leaves the middle of the dialog to the browser", () => {
    expect(trapTarget(items, "close", false)).toBeNull();
    expect(trapTarget(items, "link", false)).toBeNull();
    expect(trapTarget(items, "link", true)).toBeNull();
    expect(trapTarget(items, "submit", true)).toBeNull();
  });

  it("pulls focus back in when it is already outside", () => {
    // The state every one of these modals opens in today: focus is still on
    // the dashboard behind the overlay, so there is no index to step from.
    // Without this the first Tab of a keyboard user's visit walks INTO the
    // page the overlay is covering rather than into the dialog.
    expect(trapTarget(items, null, false)).toBe("close");
    expect(trapTarget(items, null, true)).toBe("submit");
    expect(trapTarget(items, "a-row-behind-the-overlay", false)).toBe("close");
    expect(trapTarget(items, "a-row-behind-the-overlay", true)).toBe("submit");
  });

  it("holds a dialog whose only control is the close button", () => {
    // DayDetail on a day with nothing recorded is exactly this: one ×. Both
    // directions have to land back on it, or the one modal with nothing in it
    // is the one modal you can tab out of.
    expect(trapTarget(["close"], "close", false)).toBe("close");
    expect(trapTarget(["close"], "close", true)).toBe("close");
  });

  it("does nothing with nothing to focus", () => {
    // Reachable for one render: the effect runs before the modal's children
    // are painted on a slow first paint. Returning null here is what keeps
    // that frame from swallowing the key.
    expect(trapTarget([], null, false)).toBeNull();
    expect(trapTarget([], "close", true)).toBeNull();
  });
});
