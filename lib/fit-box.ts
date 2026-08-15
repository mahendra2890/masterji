// A composer that is the height of what's in it, for both of the rooms that
// have one — the chat pane's box and the workshop's.
//
// A plain function rather than a hook: it reads and writes the DOM and closes
// over nothing, so there is nothing for a `useCallback` to stabilise. It lives
// here because the two composers are now owned by two different components —
// the chat's by the dashboard, the room's by useRoom — and a copy each is how
// the two would start to disagree about what "fits" means.

/** Size one composer to its contents, and keep the log above it pinned.
 *
 * Any fixed height is wrong in both directions at once — it sits there as an
 * empty slab on the screen whose whole point is the conversation above it, and
 * it still hides the line after the last one it has room for.
 *
 * Re-pinning the log is half the job, not a garnish. The log is the flex child
 * that gives up whatever the box takes, so a box growing by a line slides the
 * newest message up under it: you'd watch Masterji's reply leave the screen as
 * you typed your answer to it. Only re-pins a log that was already at the
 * bottom — a builder who scrolled up to re-read something keeps their place.
 */
export function fitBox(
  box: HTMLTextAreaElement | null,
  log: HTMLElement | null
) {
  // display:none, which is how the phone hides whichever pane isn't showing —
  // and how the two rooms hide each other, since only one of them is ever
  // mounted. Nothing to measure there, and measuring anyway writes a 0px
  // height onto the box that the builder then meets when they switch to it.
  if (!box || !box.offsetParent) return;
  const pinned = !!log && log.scrollHeight - log.scrollTop - log.clientHeight < 4;
  // Measured back at one row rather than at whatever the last keystroke left
  // it: scrollHeight can't report less than the height already set on the
  // element, so a box that had been tall once could only ever stay tall.
  box.style.height = "auto";
  // scrollHeight counts padding but not border, and box-sizing is border-box
  // repo-wide, so the height we set has to carry the border itself. Read off
  // the element rather than written as 2px — the border is CSS's to change.
  box.style.height = `${box.scrollHeight + box.offsetHeight - box.clientHeight}px`;
  if (log && pinned) log.scrollTop = log.scrollHeight;
}
