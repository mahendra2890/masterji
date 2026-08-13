"use client";

// The half of `aria-modal="true"` the markup cannot state.
//
// Four panels in this app open as `role="dialog"` with `aria-modal="true"` and
// an Escape handler — DayDetail, ClosedIdea, the phase drill-in, and the
// What's-new list. That attribute tells a screen reader the rest of the page is
// inert; until this file existed nothing made it so. Tab walked straight out of
// the overlay into the dashboard behind it, and closing a panel left focus
// nowhere, which for a keyboard user is the same as losing your place on the
// page.
//
// Deliberately not a focus-trap dependency: the behaviour is one wrap at each
// end and a remembered opener, and the arithmetic below is the part worth
// pinning in a test.

import { useEffect, type RefObject } from "react";

// Everything the platform lets a Tab land on. Disabled controls are skipped
// because the browser skips them, and `tabindex="-1"` is the attribute that
// means "focusable by script, never by Tab" — honouring it is what keeps a
// scroll container out of the cycle.
const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

function focusable(dialog: HTMLElement | null): HTMLElement[] {
  if (!dialog) return [];
  return Array.from(dialog.querySelectorAll<HTMLElement>(FOCUSABLE));
}

/** Where Tab should send focus, or `null` to let the browser do it.
 *
 * Generic over the element type so the decision can be tested without a DOM —
 * the only thing this needs from an element is identity, and `npm run test:web`
 * has no browser to give it, by decision rather than by omission (#117). This
 * is the pattern that decision leans on: lift the rule out, keep it generic
 * over whatever the DOM would have supplied, drive the thin remainder in a
 * browser. The two wraps are the trap; `null` in
 * the middle is what keeps the trap from breaking ordinary tabbing inside the
 * dialog, which is the failure mode of every over-eager version of this.
 */
export function trapTarget<T>(
  items: T[],
  current: T | null,
  shift: boolean,
): T | null {
  if (items.length === 0) return null;
  const at = current === null ? -1 : items.indexOf(current);
  // Focus is somewhere the dialog does not own — the page behind the overlay,
  // which is where every one of these panels opens with focus still sitting.
  // Backwards from outside means the end of the dialog, the same way it would
  // if the dialog were the whole document.
  if (at === -1) return shift ? items[items.length - 1] : items[0];
  if (shift) return at === 0 ? items[items.length - 1] : null;
  return at === items.length - 1 ? items[0] : null;
}

/** Focus in on open, Tab held inside, focus back to the opener on close.
 *
 * `trap` exists for the one case the app already has: DayDetail opens ON TOP of
 * the phase drill-in. Two panels answering Tab would fight over the same key,
 * so the one underneath stands down — the same stand-down its Escape handler
 * already does, for the same reason. Standing down is not closing, which is why
 * the opener is remembered by the effect that tracks `open` and not by the one
 * that tracks `trap`: a panel that gave up the key while a day opened over it
 * must not yank focus out of the day.
 */
export function useDialogFocus(
  ref: RefObject<HTMLElement | null>,
  open: boolean,
  trap: boolean = true,
) {
  useEffect(() => {
    if (!open) return;
    // Whatever the builder pressed to get here: a row in THE RECORD, a step in
    // the stepper, the What's-new button. Read before anything is focused, so
    // it is the page's element and not this dialog's close button.
    const opener = document.activeElement as HTMLElement | null;
    // Once, on open — not when `trap` comes back. A day closing over the
    // drill-in restores focus to the row it was opened from, and re-running
    // this would immediately take it away again.
    focusable(ref.current)[0]?.focus();
    return () => opener?.focus?.();
  }, [ref, open]);

  useEffect(() => {
    if (!open || !trap) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Tab") return;
      const target = trapTarget(
        focusable(ref.current),
        document.activeElement as HTMLElement | null,
        e.shiftKey,
      );
      if (!target) return;
      e.preventDefault();
      target.focus();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [ref, open, trap]);
}
